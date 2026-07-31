"""Dataset quality checks: schema, physics, duplicates, leakage, JSONL format."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.dataset.schemas import DatasetExample, MutationTarget, RejectionTarget, TargetKind
from backend.app.schemas.mutations import MutationSpec
from backend.app.simulator import simulate
from backend.app.simulator.mutations import apply_mutations
from backend.app.validators import validate_scenario


def _assistant_json(example: DatasetExample) -> dict[str, Any]:
    content = example.messages[-1]["content"]
    return json.loads(content)


def validate_example(example: DatasetExample) -> list[str]:
    errors: list[str] = []
    # SFT structure
    if len(example.messages) != 3:
        errors.append("messages must have length 3")
    else:
        roles = [m.get("role") for m in example.messages]
        if roles != ["system", "user", "assistant"]:
            errors.append(f"bad roles: {roles}")
        assistant = example.messages[2]["content"]
        try:
            parsed = json.loads(assistant)
        except json.JSONDecodeError as exc:
            errors.append(f"assistant JSON parse error: {exc}")
            return errors
        if parsed != example.canonical_target:
            # Allow key-order differences by comparing normalized dumps
            if json.dumps(parsed, sort_keys=True) != json.dumps(
                example.canonical_target, sort_keys=True
            ):
                errors.append("assistant content != canonical_target")

    try:
        if example.target_kind == TargetKind.MUTATION:
            MutationTarget.model_validate(example.canonical_target)
        else:
            RejectionTarget.model_validate(example.canonical_target)
    except ValidationError as exc:
        errors.append(f"canonical_target schema: {exc}")

    if example.target_kind == TargetKind.MUTATION:
        try:
            target = MutationTarget.model_validate(example.canonical_target)
            sc = example.seed_scene.model_copy(deep=True)
            sc.mutation = target.mutation
            issues = validate_scenario(sc)
            if issues:
                errors.append(
                    "physics/schema validation failed: "
                    + "; ".join(f"{i.code}:{i.message}" for i in issues)
                )
            else:
                result = simulate(sc)
                if not result.valid or result.metrics is None:
                    errors.append("simulation failed for accepted target")
                else:
                    got = [o.model_dump(mode="json") for o in result.metrics.oracle_results]
                    exp = [
                        o.model_dump(mode="json")
                        for o in example.expected_safety_oracle_results
                    ]
                    if got != exp:
                        errors.append("oracle results mismatch vs expected")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"mutation apply/sim error: {exc}")
    else:
        if example.expected_validation_result.valid:
            errors.append("rejection example must have expected_validation_result.valid=False")
        reasons = example.canonical_target.get("reasons") or []
        if not reasons:
            errors.append("rejection missing reasons")

    return errors


def validate_full_dataset(examples: list[DatasetExample]) -> dict[str, Any]:
    errors: list[str] = []
    ids = [e.id for e in examples]
    if len(ids) != len(set(ids)):
        errors.append("duplicate example ids")

    # Duplicate detection: identical assistant canonical JSON across different ids
    canon_map: dict[str, list[str]] = {}
    for e in examples:
        key = json.dumps(e.canonical_target, sort_keys=True)
        canon_map.setdefault(key, []).append(e.id)
    duplicate_targets = {k: v for k, v in canon_map.items() if len(v) > 1}
    # Duplicate targets across paraphrases can be OK for rejections templates;
    # flag only if same id pair shares seed+goal too.
    seed_goal = {}
    for e in examples:
        sg = json.dumps(
            {"seed": e.seed_scene.model_dump(mode="json"), "goal": e.testing_goal},
            sort_keys=True,
        )
        seed_goal.setdefault(sg, []).append(e.id)
    dup_sg = {k: v for k, v in seed_goal.items() if len(v) > 1}
    if dup_sg:
        errors.append(f"duplicate seed+goal pairs: {list(dup_sg.values())[:3]}")

    per_example_failures = 0
    for e in examples:
        errs = validate_example(e)
        if errs:
            per_example_failures += 1
            errors.append(f"{e.id}: " + " | ".join(errs))

    family_dist = Counter(e.scenario_family.value for e in examples)
    split_dist = Counter(e.split for e in examples)
    rejection_count = sum(1 for e in examples if e.target_kind == TargetKind.REJECTION)

    # JSONL-format validation for SFT: assistant must be pure JSON object
    jsonl_ok = True
    for e in examples:
        try:
            obj = json.loads(e.messages[2]["content"])
            if not isinstance(obj, dict):
                jsonl_ok = False
                errors.append(f"{e.id}: assistant JSON is not an object")
        except json.JSONDecodeError:
            jsonl_ok = False

    ok = per_example_failures == 0 and not dup_sg and jsonl_ok and len(ids) == len(set(ids))
    return {
        "ok": ok,
        "n_examples": len(examples),
        "per_example_failures": per_example_failures,
        "family_distribution": dict(family_dist),
        "split_distribution": dict(split_dist),
        "rejection_count": rejection_count,
        "duplicate_canonical_target_groups": len(duplicate_targets),
        "jsonl_format_ok": jsonl_ok,
        "errors": errors[:50],  # cap for report size
        "error_count": len(errors),
    }


def build_reports(
    examples: list[DatasetExample],
    validation: dict[str, Any],
    leakage: dict[str, Any],
    *,
    seed: int,
    paths: dict[str, Path],
) -> dict[str, Any]:
    family_by_split: dict[str, dict[str, int]] = {}
    for e in examples:
        family_by_split.setdefault(e.split, {})
        family_by_split[e.split][e.scenario_family.value] = (
            family_by_split[e.split].get(e.scenario_family.value, 0) + 1
        )

    dataset_report = {
        "seed": seed,
        "total_examples": len(examples),
        "splits": validation["split_distribution"],
        "scenario_family_distribution": validation["family_distribution"],
        "scenario_family_by_split": family_by_split,
        "rejection_count": validation["rejection_count"],
        "acceptance_count": len(examples) - validation["rejection_count"],
        "validation": {
            "ok": validation["ok"],
            "per_example_failures": validation["per_example_failures"],
            "jsonl_format_ok": validation["jsonl_format_ok"],
            "error_count": validation["error_count"],
            "sample_errors": validation["errors"][:20],
        },
        "files": {k: str(v) for k, v in paths.items()},
        "reproducibility": {
            "note": "Re-run scripts/generate_dataset.py --seed <seed> for identical outputs",
            "default_seed": seed,
        },
    }
    leakage_report = {
        **leakage,
        "policy": (
            "Splits are assigned by unique (road_layout, actor, trigger, hazard) "
            "composition fingerprints so train/test paraphrases cannot leak compositions."
        ),
    }
    return {"dataset_report": dataset_report, "leakage_report": leakage_report}


def load_jsonl(path: Path) -> list[DatasetExample]:
    examples: list[DatasetExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        examples.append(DatasetExample.model_validate_json(line))
    return examples
