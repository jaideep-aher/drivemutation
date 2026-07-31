"""Evaluate a chat model on a Stage 2 split with shared metrics + latency/tokens."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

from backend.app.dataset.schemas import DatasetExample
from backend.app.dataset.validate_dataset import load_jsonl
from backend.app.eval.metrics import evaluate_prediction
from backend.app.openai_ft.client import get_client
from backend.app.openai_ft.compile import chat_complete
from backend.app.openai_ft.config import EVAL_TEMPERATURE, Stage3Config, load_config


def _aggregate(
    rows: list[dict[str, Any]],
    examples: list[DatasetExample],
) -> dict[str, Any]:
    by_id = {e.id: e for e in examples}

    def rate(key: str, subset: list[dict[str, Any]]) -> float:
        if not subset:
            return 0.0
        return sum(1 for r in subset if r.get(key)) / len(subset)

    gold_acc = [
        r
        for r in rows
        if by_id[r["example_id"]].target_kind.value == "mutation"
    ]
    gold_rej = [
        r
        for r in rows
        if by_id[r["example_id"]].target_kind.value == "rejection"
    ]

    latencies = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    prompt_tokens = [
        r["usage"]["prompt_tokens"]
        for r in rows
        if r.get("usage") and r["usage"].get("prompt_tokens") is not None
    ]
    completion_tokens = [
        r["usage"]["completion_tokens"]
        for r in rows
        if r.get("usage") and r["usage"].get("completion_tokens") is not None
    ]
    total_tokens = [
        r["usage"]["total_tokens"]
        for r in rows
        if r.get("usage") and r["usage"].get("total_tokens") is not None
    ]

    return {
        "n": len(rows),
        "json_parse_rate": rate("json_parse_ok", rows),
        "schema_valid_rate": rate("schema_valid", rows),
        "physical_validity_rate": rate("physical_valid", gold_acc) if gold_acc else 0.0,
        "scenario_family_accuracy": rate("scenario_family_correct", gold_acc)
        if gold_acc
        else 0.0,
        "hazard_activation_rate": rate("hazard_activation_correct", gold_acc)
        if gold_acc
        else 0.0,
        "oracle_correctness": rate("oracle_correct", gold_acc) if gold_acc else 0.0,
        "impossible_request_rejection_accuracy": rate("rejection_correct", gold_rej)
        if gold_rej
        else 0.0,
        "latency": {
            "mean_s": sum(latencies) / len(latencies) if latencies else None,
            "p50_s": sorted(latencies)[len(latencies) // 2] if latencies else None,
            "max_s": max(latencies) if latencies else None,
            "n": len(latencies),
        },
        "token_use": {
            "prompt_tokens_total": sum(prompt_tokens) if prompt_tokens else 0,
            "completion_tokens_total": sum(completion_tokens) if completion_tokens else 0,
            "total_tokens": sum(total_tokens) if total_tokens else 0,
            "mean_total_tokens": (sum(total_tokens) / len(total_tokens))
            if total_tokens
            else None,
        },
        "api_error_count": sum(1 for r in rows if r.get("api_error")),
    }


def evaluate_model_on_split(
    *,
    model: str,
    processed_dir: Path,
    outputs_dir: Path,
    split: str = "test",
    client: OpenAI | None = None,
    config: Stage3Config | None = None,
    label: str | None = None,
    limit: int | None = None,
    temperature: float = EVAL_TEMPERATURE,
) -> dict[str, Any]:
    """Run identical eval protocol for base or fine-tuned model."""
    cfg = config or load_config()
    cli = client or get_client(cfg)
    examples = load_jsonl(processed_dir / f"{split}.jsonl")
    if limit is not None:
        examples = examples[:limit]

    rows: list[dict[str, Any]] = []
    predictions: dict[str, str] = {}

    for ex in examples:
        system = ex.messages[0]["content"]
        user = ex.messages[1]["content"]
        chat = chat_complete(
            model=model,
            system=system,
            user=user,
            client=cli,
            temperature=temperature,
        )
        text = chat.get("text") or ""
        predictions[ex.id] = text
        scored = evaluate_prediction(ex, text)
        scored["latency_s"] = chat.get("latency_s")
        scored["usage"] = chat.get("usage")
        scored["api_error"] = None if chat.get("ok") else chat.get("error_code")
        scored["api_error_detail"] = None if chat.get("ok") else chat.get("error")
        # If API failed, mark parse false explicitly
        if not chat.get("ok"):
            scored["json_parse_ok"] = False
            scored["schema_valid"] = False
        rows.append(scored)

    summary = _aggregate(rows, examples)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = label or model.replace(":", "_").replace("/", "_")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = outputs_dir / f"eval_{tag}_{split}_{stamp}.json"
    latest_path = outputs_dir / f"eval_{tag}_{split}_latest.json"

    payload = {
        "model": model,
        "label": label or tag,
        "split": split,
        "temperature": temperature,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {k: v for k, v in summary.items()},
        "rows": rows,
        "predictions": predictions,
    }
    text = json.dumps(payload, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    summary_out = {
        "model": model,
        "label": label or tag,
        "split": split,
        "path": str(out_path),
        "latest_path": str(latest_path),
        **summary,
    }
    return summary_out


def load_latest_eval_summary(outputs_dir: Path) -> dict[str, Any]:
    """Load latest base + fine-tuned eval summaries if present.

    Never invents metrics. Missing files yield null fields and available=false.
    """
    methodology = {
        "test_set": "Stage 2 untouched test split (data/processed/test.jsonl)",
        "test_set_size": None,
        "temperature": EVAL_TEMPERATURE,
        "protocol": (
            "Identical system prompt, user messages, temperature=0, parsing, "
            "schema/physics validation, and offline metrics for base and fine-tuned."
        ),
        "notes": (
            "Metrics are measured only. If a file is missing, that block is null  -  "
            "not a zero score."
        ),
    }
    test_jsonl = outputs_dir.parent / "processed" / "test.jsonl"
    if test_jsonl.is_file():
        methodology["test_set_size"] = sum(
            1 for line in test_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    result: dict[str, Any] = {
        "available": False,
        "base": None,
        "fine_tuned": None,
        "comparison": None,
        "methodology": methodology,
    }
    base = outputs_dir / "eval_base_test_latest.json"
    ft = outputs_dir / "eval_fine_tuned_test_latest.json"
    cmp = outputs_dir / "compare_base_vs_finetuned_latest.json"
    if base.is_file():
        data = json.loads(base.read_text(encoding="utf-8"))
        result["base"] = {
            "model": data.get("model"),
            "label": data.get("label"),
            "split": data.get("split"),
            "metrics": data.get("metrics"),
            "created_at": data.get("created_at"),
            "n": (data.get("metrics") or {}).get("n"),
        }
    if ft.is_file():
        data = json.loads(ft.read_text(encoding="utf-8"))
        result["fine_tuned"] = {
            "model": data.get("model"),
            "label": data.get("label"),
            "split": data.get("split"),
            "metrics": data.get("metrics"),
            "created_at": data.get("created_at"),
            "n": (data.get("metrics") or {}).get("n"),
        }
    if cmp.is_file():
        result["comparison"] = json.loads(cmp.read_text(encoding="utf-8"))
    result["available"] = bool(result["base"] or result["fine_tuned"] or result["comparison"])
    return result
