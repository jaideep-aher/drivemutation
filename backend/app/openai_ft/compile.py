"""Compile seed scene + testing goal via OpenAI chat completions (server-side)."""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from openai import APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError

from backend.app.dataset.schemas import (
    FAMILY_TO_HAZARD,
    HazardKind,
    SYSTEM_PROMPT,
    MutationTarget,
    RejectionTarget,
    ScenarioFamily,
    build_sft_messages,
)
from backend.app.openai_ft.client import MissingAPIKeyError, get_client
from backend.app.openai_ft.config import (
    EVAL_MAX_TOKENS,
    EVAL_TEMPERATURE,
    Stage3Config,
    load_config,
)
from backend.app.schemas.common import MutationOp
from backend.app.schemas.scenario import ScenarioSpec, ValidationIssue
from backend.app.simulator import simulate
from backend.app.validators import validate_scenario

CompileMode = Literal["base", "fine-tuned"]

_VALID_OPS = {m.value for m in MutationOp}

_OP_ALIASES: dict[str, str] = {
    "set_actor_behavior": "change_behavior",
    "modify_behavior": "change_behavior",
    "update_behavior": "change_behavior",
    "set_behavior": "change_behavior",
    "move_actor": "shift_position",
    "set_position": "shift_position",
    "set_velocity": "set_speed",
    "change_speed": "set_speed",
    "spawn_actor": "add_actor",
    "delete_actor": "remove_actor",
    "set_trigger_time": "change_trigger_time",
}


def _parse_assistant_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"malformed_json: {exc}"
    if not isinstance(obj, dict):
        return None, "malformed_json: root must be object"
    return obj, None


_HAZARD_TO_FAMILY: dict[str, str] = {h.value: f.value for f, h in FAMILY_TO_HAZARD.items()}


def _normalize_mutation_target(
    parsed: dict[str, Any],
    seed_actor_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Fix common model mix-ups before strict validation."""
    d = json.loads(json.dumps(parsed))
    existing_ids = seed_actor_ids or set()

    sf = d.get("scenario_family", "")
    if sf and sf not in {m.value for m in ScenarioFamily}:
        if sf in _HAZARD_TO_FAMILY:
            d["scenario_family"] = _HAZARD_TO_FAMILY[sf]
    ah = d.get("activated_hazard", "")
    if ah and ah not in {m.value for m in HazardKind}:
        if ah in {m.value for m in ScenarioFamily}:
            mapped = FAMILY_TO_HAZARD.get(ScenarioFamily(ah))
            if mapped:
                d["activated_hazard"] = mapped.value
    if "status" not in d and "mutation" in d:
        d["status"] = "accepted"

    mutation = d.get("mutation")
    if isinstance(mutation, dict):
        ops = mutation.get("operations", [])
        added_actor_ids: set[str] = set()

        for op in ops:
            if not isinstance(op, dict):
                continue
            if op.get("op") not in _VALID_OPS:
                canonical = _OP_ALIASES.get(op["op"])
                if canonical:
                    op["op"] = canonical
            if op.get("op") == "add_actor" and isinstance(op.get("actor"), dict):
                added_actor_ids.add(op["actor"].get("id", ""))

        cleaned: list[dict[str, Any]] = []
        for op in ops:
            if not isinstance(op, dict):
                cleaned.append(op)
                continue
            opname = op.get("op")
            aid = op.get("actor_id")

            if opname == "add_actor" and isinstance(op.get("actor"), dict):
                actor_id = op["actor"].get("id", "")
                if actor_id in existing_ids:
                    # Actor already exists in seed -- convert to change_behavior
                    actor_data = op["actor"]
                    behavior = actor_data.get("behavior")
                    if behavior:
                        cleaned.append({
                            "op": "change_behavior",
                            "actor_id": actor_id,
                            "behavior": behavior,
                        })
                    continue
            if opname == "change_behavior" and not op.get("behavior"):
                actor_data = op.get("actor")
                if isinstance(actor_data, dict) and actor_data.get("behavior"):
                    op["behavior"] = actor_data["behavior"]
                    if not aid and actor_data.get("id"):
                        op["actor_id"] = actor_data["id"]
                    op["actor"] = None
                elif aid in added_actor_ids:
                    continue
            if opname == "set_speed" and aid in added_actor_ids:
                continue
            if opname == "shift_position" and aid in added_actor_ids:
                continue
            cleaned.append(op)
        mutation["operations"] = cleaned

    return d


def _validate_target(
    parsed: dict[str, Any],
    seed_actor_ids: set[str] | None = None,
) -> tuple[MutationTarget | RejectionTarget | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    try:
        if parsed.get("status") == "rejected":
            return RejectionTarget.model_validate(parsed), issues
        normalized = _normalize_mutation_target(parsed, seed_actor_ids)
        if normalized.get("status") == "accepted" or "mutation" in normalized:
            return MutationTarget.model_validate(normalized), issues
        try:
            return RejectionTarget.model_validate(parsed), issues
        except ValidationError:
            return MutationTarget.model_validate(normalized), issues
    except ValidationError as exc:
        issues.append(
            ValidationIssue(
                code="schema_invalid",
                message=str(exc),
                path="assistant",
            )
        )
        return None, issues


def resolve_model_id(mode: CompileMode, config: Stage3Config | None = None) -> str:
    cfg = config or load_config()
    if mode == "base":
        return cfg.base_model
    if not cfg.fine_tuned_configured:
        raise ValueError("OPENAI_FINE_TUNED_MODEL is not configured")
    return cfg.fine_tuned_model


def chat_complete(
    *,
    model: str,
    system: str,
    user: str,
    client: OpenAI | None = None,
    temperature: float = EVAL_TEMPERATURE,
    max_tokens: int = EVAL_MAX_TOKENS,
) -> dict[str, Any]:
    """Call chat.completions; returns text + usage + latency (no secrets)."""
    cli = client or get_client()
    t0 = time.perf_counter()
    try:
        resp = cli.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except MissingAPIKeyError:
        raise
    except APITimeoutError as exc:
        return {
            "ok": False,
            "error_code": "timeout",
            "error": str(exc),
            "latency_s": time.perf_counter() - t0,
            "text": None,
            "usage": None,
        }
    except RateLimitError as exc:
        return {
            "ok": False,
            "error_code": "rate_limit",
            "error": str(exc),
            "latency_s": time.perf_counter() - t0,
            "text": None,
            "usage": None,
        }
    except APIError as exc:
        return {
            "ok": False,
            "error_code": "api_error",
            "error": str(exc),
            "latency_s": time.perf_counter() - t0,
            "text": None,
            "usage": None,
        }
    except Exception as exc:  # noqa: BLE001  -  surface as api_failure
        return {
            "ok": False,
            "error_code": "api_failure",
            "error": str(exc),
            "latency_s": time.perf_counter() - t0,
            "text": None,
            "usage": None,
        }

    latency = time.perf_counter() - t0
    choice = resp.choices[0] if resp.choices else None
    text = choice.message.content if choice and choice.message else None
    usage = None
    if resp.usage is not None:
        usage = {
            "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
            "completion_tokens": getattr(resp.usage, "completion_tokens", None),
            "total_tokens": getattr(resp.usage, "total_tokens", None),
        }
    return {
        "ok": True,
        "error_code": None,
        "error": None,
        "latency_s": latency,
        "text": text or "",
        "usage": usage,
        "finish_reason": getattr(choice, "finish_reason", None) if choice else None,
    }


def compile_scenario(
    *,
    seed_scene: ScenarioSpec,
    testing_goal: str,
    mode: CompileMode = "base",
    client: OpenAI | None = None,
    config: Stage3Config | None = None,
    run_simulation: bool = True,
) -> dict[str, Any]:
    """Compile a mutation/rejection; invalid output never reaches the simulator."""
    cfg = config or load_config()
    result: dict[str, Any] = {
        "mode": mode,
        "model": None,
        "ok": False,
        "error_code": None,
        "error": None,
        "raw_text": None,
        "parsed": None,
        "target_kind": None,
        "json_parse_ok": False,
        "schema_valid": False,
        "physical_valid": False,
        "validation_issues": [],
        "simulation": None,
        "latency_s": None,
        "usage": None,
    }

    try:
        model = resolve_model_id(mode, cfg)
    except ValueError as exc:
        result["error_code"] = "missing_model_config"
        result["error"] = str(exc)
        return result
    result["model"] = model

    if not cfg.api_key_configured and client is None:
        result["error_code"] = "missing_api_key"
        result["error"] = "OPENAI_API_KEY is not configured"
        return result

    msgs = build_sft_messages(seed_scene, testing_goal, assistant_json="{}")
    system = msgs[0]["content"] or SYSTEM_PROMPT
    user = msgs[1]["content"]

    try:
        chat = chat_complete(
            model=model,
            system=system,
            user=user,
            client=client,
        )
    except MissingAPIKeyError:
        result["error_code"] = "missing_api_key"
        result["error"] = "OPENAI_API_KEY is not configured"
        return result

    result["latency_s"] = chat.get("latency_s")
    result["usage"] = chat.get("usage")
    if not chat.get("ok"):
        result["error_code"] = chat.get("error_code") or "api_failure"
        result["error"] = chat.get("error")
        return result

    text = chat.get("text") or ""
    result["raw_text"] = text
    parsed, parse_err = _parse_assistant_json(text)
    if parse_err or parsed is None:
        result["error_code"] = "malformed_json"
        result["error"] = parse_err
        result["json_parse_ok"] = False
        return result
    result["json_parse_ok"] = True
    result["parsed"] = parsed

    seed_ids = {a.id for a in seed_scene.actors} if seed_scene.actors else set()
    target, schema_issues = _validate_target(parsed, seed_ids)
    if target is None:
        result["error_code"] = "schema_invalid"
        result["error"] = "assistant output failed schema validation"
        result["validation_issues"] = [i.model_dump(mode="json") for i in schema_issues]
        return result
    result["schema_valid"] = True

    if isinstance(target, RejectionTarget):
        result["target_kind"] = "rejection"
        result["ok"] = True
        result["physical_valid"] = False  # N/A  -  not simulated
        return result

    result["target_kind"] = "mutation"
    sc = seed_scene.model_copy(deep=True)
    sc.mutation = target.mutation
    issues = validate_scenario(sc)
    result["validation_issues"] = [i.model_dump(mode="json") for i in issues]
    if issues:
        result["error_code"] = "physically_invalid"
        result["error"] = "compiled mutation failed physical validation"
        result["physical_valid"] = False
        # Never simulate
        return result

    result["physical_valid"] = True
    if run_simulation:
        sim = simulate(sc)
        result["simulation"] = sim.model_dump(mode="json")
        if not sim.valid:
            result["error_code"] = "simulation_invalid"
            result["error"] = "simulation rejected scenario"
            return result
    result["ok"] = True
    result["parsed"] = target.model_dump(mode="json")
    return result
