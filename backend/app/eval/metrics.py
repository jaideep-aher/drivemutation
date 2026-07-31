"""Offline evaluation metrics for DriveMutation Stage 2."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from backend.app.dataset.schemas import (
    DatasetExample,
    HazardKind,
    MutationTarget,
    RejectionTarget,
    ScenarioFamily,
    TargetKind,
)
from backend.app.schemas.mutations import MutationSpec
from backend.app.schemas.scenario import ScenarioSpec
from backend.app.simulator import simulate
from backend.app.validators import validate_scenario


def _parse_assistant(text: str) -> tuple[dict[str, Any] | None, bool]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(obj, dict):
        return None, False
    return obj, True


def evaluate_prediction(
    example: DatasetExample,
    prediction_text: str,
) -> dict[str, Any]:
    """Score one model/compiler prediction against a gold example."""
    parsed, json_ok = _parse_assistant(prediction_text)
    result: dict[str, Any] = {
        "example_id": example.id,
        "json_parse_ok": json_ok,
        "schema_valid": False,
        "physical_valid": False,
        "scenario_family_correct": False,
        "hazard_activation_correct": False,
        "oracle_correct": False,
        "rejection_correct": False,
        "predicted_kind": None,
    }
    if not json_ok or parsed is None:
        return result

    # Schema: accepted mutation or rejection
    pred_mut: MutationTarget | None = None
    pred_rej: RejectionTarget | None = None
    try:
        if parsed.get("status") == "rejected":
            pred_rej = RejectionTarget.model_validate(parsed)
            result["predicted_kind"] = "rejection"
            result["schema_valid"] = True
        elif parsed.get("status") == "accepted" or "mutation" in parsed:
            pred_mut = MutationTarget.model_validate(parsed)
            result["predicted_kind"] = "mutation"
            result["schema_valid"] = True
        else:
            # Try mutation spec nested forms
            try:
                pred_rej = RejectionTarget.model_validate(parsed)
                result["predicted_kind"] = "rejection"
                result["schema_valid"] = True
            except ValidationError:
                pred_mut = MutationTarget.model_validate(parsed)
                result["predicted_kind"] = "mutation"
                result["schema_valid"] = True
    except ValidationError:
        result["schema_valid"] = False
        return result

    gold_is_rej = example.target_kind == TargetKind.REJECTION

    if gold_is_rej:
        result["rejection_correct"] = pred_rej is not None
        if pred_rej is not None:
            gold_codes = {r["code"] for r in example.canonical_target.get("reasons", [])}
            pred_codes = {r.code for r in pred_rej.reasons}
            result["rejection_correct"] = bool(gold_codes & pred_codes) or pred_codes == gold_codes
        return result

    # Gold accepted
    if pred_mut is None:
        result["rejection_correct"] = False
        return result

    result["scenario_family_correct"] = (
        pred_mut.scenario_family == example.expected_scenario_family
    )
    result["hazard_activation_correct"] = (
        example.expected_activated_hazard is not None
        and pred_mut.activated_hazard == example.expected_activated_hazard
    )

    sc = example.seed_scene.model_copy(deep=True)
    sc.mutation = pred_mut.mutation
    issues = validate_scenario(sc)
    result["physical_valid"] = len(issues) == 0
    if issues:
        return result

    sim = simulate(sc)
    if not sim.valid or sim.metrics is None:
        result["physical_valid"] = False
        return result

    got = [o.model_dump(mode="json") for o in sim.metrics.oracle_results]
    exp = [o.model_dump(mode="json") for o in example.expected_safety_oracle_results]
    # Oracle correctness: same pass/fail per oracle id when ids match; else compare full
    if len(got) == len(exp):
        result["oracle_correct"] = all(
            g.get("id") == e.get("id") and g.get("passed") == e.get("passed")
            for g, e in zip(got, exp)
        )
    else:
        result["oracle_correct"] = got == exp
    return result


def evaluate_dataset(
    examples: list[DatasetExample],
    predictions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate predictions; if predictions is None, score gold assistant messages (sanity)."""
    rows = []
    for ex in examples:
        if predictions is None:
            pred = ex.messages[2]["content"]
        else:
            pred = predictions.get(ex.id, "")
        rows.append(evaluate_prediction(ex, pred))

    def rate(key: str, subset: list[dict] | None = None) -> float:
        data = subset if subset is not None else rows
        if not data:
            return 0.0
        return sum(1 for r in data if r[key]) / len(data)

    accepted_rows = [r for r in rows if r["predicted_kind"] == "mutation" or (
        next(e for e in examples if e.id == r["example_id"]).target_kind == TargetKind.MUTATION
    )]
    # Clarify subsets by gold label
    gold_acc = [
        r
        for r in rows
        if next(e for e in examples if e.id == r["example_id"]).target_kind
        == TargetKind.MUTATION
    ]
    gold_rej = [
        r
        for r in rows
        if next(e for e in examples if e.id == r["example_id"]).target_kind
        == TargetKind.REJECTION
    ]

    return {
        "n": len(rows),
        "json_parse_rate": rate("json_parse_ok"),
        "schema_valid_rate": rate("schema_valid"),
        "physical_validity_rate": rate("physical_valid", gold_acc) if gold_acc else 0.0,
        "scenario_family_accuracy": rate("scenario_family_correct", gold_acc) if gold_acc else 0.0,
        "hazard_activation_rate": rate("hazard_activation_correct", gold_acc) if gold_acc else 0.0,
        "oracle_correctness": rate("oracle_correct", gold_acc) if gold_acc else 0.0,
        "impossible_request_rejection_accuracy": rate("rejection_correct", gold_rej)
        if gold_rej
        else 0.0,
        "rows": rows,
    }
