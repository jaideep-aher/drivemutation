"""Stage 2 dataset and evaluation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.dataset.compositions import (
    DEFAULT_SEED,
    N_TEST,
    N_TRAIN,
    N_VAL,
    assign_splits,
    build_composition_catalog,
    leakage_check,
)
from backend.app.dataset.generate import file_sha256, generate_and_write, generate_dataset
from backend.app.dataset.schemas import ScenarioFamily, TargetKind
from backend.app.dataset.validate_dataset import load_jsonl, validate_example, validate_full_dataset
from backend.app.eval.metrics import evaluate_dataset
from backend.app.eval.harness import run_offline_eval

ROOT = Path(__file__).resolve().parents[1]


def test_composition_catalog_unique_and_sized():
    catalog = build_composition_catalog(seed=DEFAULT_SEED)
    assert len(catalog) == N_TRAIN + N_VAL + N_TEST
    fps = [c[1].fingerprint() for c in catalog]
    assert len(fps) == len(set(fps))
    families = {c[0] for c in catalog}
    assert families == set(ScenarioFamily)
    assert sum(1 for c in catalog if c[3]) == 30


def test_splits_and_no_train_test_leakage():
    catalog = build_composition_catalog(seed=DEFAULT_SEED)
    plans = assign_splits(catalog, seed=DEFAULT_SEED)
    assert sum(1 for p in plans if p.split == "train") == N_TRAIN
    assert sum(1 for p in plans if p.split == "validation") == N_VAL
    assert sum(1 for p in plans if p.split == "test") == N_TEST
    leak = leakage_check(plans)
    assert leak["has_train_test_leakage"] is False
    assert leak["has_any_cross_split_leakage"] is False
    assert leak["unique_compositions"] == 180


def test_generate_dataset_in_memory():
    examples = generate_dataset(seed=DEFAULT_SEED)
    assert len(examples) == 180
    assert sum(1 for e in examples if e.split == "train") == 120
    assert sum(1 for e in examples if e.target_kind == TargetKind.REJECTION) == 30
    report = validate_full_dataset(examples)
    assert report["ok"] is True
    assert report["per_example_failures"] == 0


def test_accepted_targets_pass_schema_and_physics():
    examples = generate_dataset(seed=DEFAULT_SEED)
    accepted = [e for e in examples if e.target_kind == TargetKind.MUTATION]
    assert len(accepted) == 150
    for e in accepted[:20]:  # sample + full validate_full already covers all
        errs = validate_example(e)
        assert errs == [], (e.id, errs)
    # Spot-check rejections have reasons
    for e in examples:
        if e.target_kind == TargetKind.REJECTION:
            assert e.canonical_target.get("status") == "rejected"
            assert e.canonical_target.get("reasons")
            assert e.expected_validation_result.valid is False


def test_reproducibility_same_seed(tmp_path: Path):
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    s1 = generate_and_write(out1 / "processed", out1 / "outputs", seed=DEFAULT_SEED)
    s2 = generate_and_write(out2 / "processed", out2 / "outputs", seed=DEFAULT_SEED)
    assert s1["sha256"] == s2["sha256"]
    for name in ("train", "validation", "test"):
        p1 = out1 / "processed" / f"{name}.jsonl"
        p2 = out2 / "processed" / f"{name}.jsonl"
        assert p1.read_bytes() == p2.read_bytes()
        assert file_sha256(p1) == file_sha256(p2)


def test_sft_jsonl_format_assistant_only_json(tmp_path: Path):
    summary = generate_and_write(tmp_path / "processed", tmp_path / "outputs", seed=DEFAULT_SEED)
    for name in ("train", "validation", "test"):
        path = Path(summary["paths"][name])
        for line in path.read_text(encoding="utf-8").splitlines():
            ex = json.loads(line)
            msgs = ex["messages"]
            assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
            obj = json.loads(msgs[2]["content"])
            assert isinstance(obj, dict)
            assert obj.get("status") in {"accepted", "rejected"}


def test_offline_eval_gold_perfect(tmp_path: Path):
    generate_and_write(tmp_path / "processed", tmp_path / "outputs", seed=DEFAULT_SEED)
    examples = load_jsonl(tmp_path / "processed" / "test.jsonl")
    report = evaluate_dataset(examples, predictions=None)
    assert report["json_parse_rate"] == 1.0
    assert report["schema_valid_rate"] == 1.0
    assert report["physical_validity_rate"] == 1.0
    assert report["scenario_family_accuracy"] == 1.0
    assert report["hazard_activation_rate"] == 1.0
    assert report["oracle_correctness"] == 1.0
    assert report["impossible_request_rejection_accuracy"] == 1.0

    summary = run_offline_eval(tmp_path / "processed", tmp_path / "outputs", split="test")
    assert summary["json_parse_rate"] == 1.0
    assert (tmp_path / "outputs" / "eval_test.json").is_file()


def test_processed_artifacts_exist_after_script():
    """If repo artifacts exist, they must be valid; otherwise generate into check."""
    processed = ROOT / "data" / "processed"
    required = [processed / "train.jsonl", processed / "validation.jsonl", processed / "test.jsonl"]
    if all(p.is_file() and p.stat().st_size > 0 for p in required):
        examples = []
        for p in required:
            examples.extend(load_jsonl(p))
        assert len(examples) == 180
        assert validate_full_dataset(examples)["ok"]
        report = ROOT / "data" / "outputs" / "dataset_report.json"
        leak = ROOT / "data" / "outputs" / "leakage_report.json"
        assert report.is_file() and leak.is_file()
        leak_data = json.loads(leak.read_text(encoding="utf-8"))
        assert leak_data["has_train_test_leakage"] is False
    else:
        pytest.skip("processed artifacts not present; generation covered elsewhere")
