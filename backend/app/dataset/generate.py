"""Deterministic Stage-2 dataset generator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.app.dataset.compositions import (
    DEFAULT_SEED,
    N_TEST,
    N_TRAIN,
    N_VAL,
    ExamplePlan,
    assign_splits,
    build_composition_catalog,
    leakage_check,
)
from backend.app.dataset.paraphrase import paraphrase_goal
from backend.app.dataset.scenes import build_seed_scene
from backend.app.dataset.schemas import (
    DatasetExample,
    ExpectedValidation,
    TargetKind,
    build_sft_messages,
)
from backend.app.dataset.targets import (
    build_accepted_target,
    build_rejection_target,
    target_to_canonical_json,
)
from backend.app.dataset.validate_dataset import build_reports, validate_full_dataset
from backend.app.schemas.common import Assumption, Unknown
from backend.app.schemas.mutations import MutationSpec
from backend.app.schemas.scenario import ScenarioSpec, ValidationIssue
from backend.app.simulator import simulate
from backend.app.validators import validate_scenario


def _example_id(plan: ExamplePlan) -> str:
    raw = (
        f"{plan.split}:{plan.family.value}:{plan.composition.fingerprint()}:"
        f"{plan.variant}:{plan.is_rejection}"
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"dm2_{plan.split[:3]}_{plan.family.value}_{digest}"


def _apply_target_mutation(seed: ScenarioSpec, mutation: MutationSpec) -> ScenarioSpec:
    sc = seed.model_copy(deep=True)
    sc.mutation = mutation
    return sc


def build_example(plan: ExamplePlan) -> DatasetExample:
    eid = _example_id(plan)
    seed = build_seed_scene(
        example_id=eid,
        family=plan.family,
        road_kind=plan.composition.road_layout,
        actor_kind=plan.composition.actor,
        trigger_kind=plan.composition.trigger,
        variant=plan.variant,
    )

    actor_label = plan.composition.actor.value.replace("_", " ")
    testing_goal = paraphrase_goal(
        plan.family,
        plan.variant,
        impossible=plan.is_rejection,
        actor_label=actor_label,
    )

    assumptions = list(seed.assumptions) + [
        Assumption(
            id="a_stage2_compiler",
            statement="Canonical targets are produced by deterministic code, not an LLM.",
        )
    ]
    unknowns = list(seed.unknowns) + [
        Unknown(
            id="u_nl_ambiguity",
            statement=(
                "Natural-language goals may admit multiple mutations; "
                "only the canonical target is supervised."
            ),
        )
    ]

    if plan.is_rejection:
        target = build_rejection_target(variant=plan.variant, actor_label=actor_label)
        canonical = target.model_dump(mode="json")
        assistant_json = target_to_canonical_json(target)
        expected_validation = ExpectedValidation(
            valid=False,
            issues=[
                ValidationIssue(code=r.code, message=r.message) for r in target.reasons
            ],
        )
        oracle_results: list = []
        hazard = None
        target_kind = TargetKind.REJECTION
    else:
        target = build_accepted_target(
            example_id=eid,
            family=plan.family,
            road_kind=plan.composition.road_layout,
            actor_kind=plan.composition.actor,
            trigger_kind=plan.composition.trigger,
            variant=plan.variant,
            seed=seed,
        )
        canonical = target.model_dump(mode="json")
        assistant_json = target_to_canonical_json(target)
        mutated = _apply_target_mutation(seed, target.mutation)
        issues = validate_scenario(mutated)
        if issues:
            raise RuntimeError(
                f"Accepted target failed validation for {eid}: "
                + "; ".join(f"{i.code}:{i.message}" for i in issues)
            )
        result = simulate(mutated)
        assert result.metrics is not None
        expected_validation = ExpectedValidation(valid=True, issues=[])
        oracle_results = list(result.metrics.oracle_results)
        hazard = target.activated_hazard
        target_kind = TargetKind.MUTATION

    messages = build_sft_messages(seed, testing_goal, assistant_json)
    return DatasetExample(
        id=eid,
        split=plan.split,  # type: ignore[arg-type]
        scenario_family=plan.family,
        composition=plan.composition,
        target_kind=target_kind,
        seed_scene=seed,
        testing_goal=testing_goal,
        canonical_target=canonical,
        expected_scenario_family=plan.family,
        expected_activated_hazard=hazard,
        expected_validation_result=expected_validation,
        expected_safety_oracle_results=oracle_results,
        assumptions=assumptions,
        unknowns=unknowns,
        messages=messages,
    )


def generate_dataset(seed: int = DEFAULT_SEED) -> list[DatasetExample]:
    catalog = build_composition_catalog(seed=seed)
    plans = assign_splits(catalog, seed=seed)
    return [build_example(p) for p in plans]


def write_jsonl(path: Path, examples: list[DatasetExample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ex.model_dump_json() for ex in examples]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def generate_and_write(
    processed_dir: Path,
    outputs_dir: Path,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Generate dataset, write JSONL + reports, return summary dict."""
    examples = generate_dataset(seed=seed)
    by_split = {
        "train": [e for e in examples if e.split == "train"],
        "validation": [e for e in examples if e.split == "validation"],
        "test": [e for e in examples if e.split == "test"],
    }
    assert len(by_split["train"]) == N_TRAIN
    assert len(by_split["validation"]) == N_VAL
    assert len(by_split["test"]) == N_TEST

    processed_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for name, subset in by_split.items():
        p = processed_dir / f"{name}.jsonl"
        write_jsonl(p, subset)
        paths[name] = p

    validation = validate_full_dataset(examples)
    plans = [
        ExamplePlan(
            index=i,
            split=e.split,
            family=e.scenario_family,
            composition=e.composition,
            variant=0,
            is_rejection=e.target_kind == TargetKind.REJECTION,
        )
        for i, e in enumerate(examples)
    ]
    leak = leakage_check(plans)
    reports = build_reports(examples, validation, leak, seed=seed, paths=paths)

    dataset_report_path = outputs_dir / "dataset_report.json"
    leakage_report_path = outputs_dir / "leakage_report.json"
    dataset_report_path.write_text(
        json.dumps(reports["dataset_report"], indent=2) + "\n", encoding="utf-8"
    )
    leakage_report_path.write_text(
        json.dumps(reports["leakage_report"], indent=2) + "\n", encoding="utf-8"
    )

    if not validation["ok"]:
        raise RuntimeError(f"Dataset validation failed: {json.dumps(validation, indent=2)}")

    if leak["has_train_test_leakage"]:
        raise RuntimeError(f"Train/test leakage detected: {leak['train_test_overlap']}")

    return {
        "seed": seed,
        "counts": {k: len(v) for k, v in by_split.items()},
        "paths": {k: str(v) for k, v in paths.items()},
        "dataset_report": str(dataset_report_path),
        "leakage_report": str(leakage_report_path),
        "sha256": {k: file_sha256(v) for k, v in paths.items()},
        "validation": validation,
        "leakage": leak,
    }
