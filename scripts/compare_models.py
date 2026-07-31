#!/usr/bin/env python3
"""Compare base vs fine-tuned evaluation summaries on the same test set."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.openai_ft.config import load_config
from backend.app.openai_ft.evaluate import evaluate_model_on_split
from backend.app.openai_ft.state import load_state

METRIC_KEYS = [
    "json_parse_rate",
    "schema_valid_rate",
    "physical_validity_rate",
    "scenario_family_accuracy",
    "hazard_activation_rate",
    "oracle_correctness",
    "impossible_request_rejection_accuracy",
]


def _metrics_from_eval(summary: dict[str, Any]) -> dict[str, Any]:
    return {k: summary.get(k) for k in METRIC_KEYS} | {
        "latency": summary.get("latency"),
        "token_use": summary.get("token_use"),
        "n": summary.get("n"),
        "api_error_count": summary.get("api_error_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Run both evals before compare")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=ROOT / "data" / "processed",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=ROOT / "data" / "outputs",
    )
    parser.add_argument("--base-eval", type=Path, default=None)
    parser.add_argument("--ft-eval", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config()
    outputs = args.outputs_dir
    outputs.mkdir(parents=True, exist_ok=True)

    base_summary = None
    ft_summary = None

    if args.run:
        if not cfg.api_key_configured:
            print(json.dumps({"ok": False, "error": "OPENAI_API_KEY not configured"}))
            return 2
        state = load_state(cfg.state_path)
        ft_model = cfg.fine_tuned_model or state.fine_tuned_model
        if not ft_model:
            print(json.dumps({"ok": False, "error": "fine-tuned model not available"}))
            return 2
        base_summary = evaluate_model_on_split(
            model=cfg.base_model,
            processed_dir=args.processed_dir,
            outputs_dir=outputs,
            split="test",
            config=cfg,
            label="base",
            limit=args.limit,
        )
        ft_summary = evaluate_model_on_split(
            model=ft_model,
            processed_dir=args.processed_dir,
            outputs_dir=outputs,
            split="test",
            config=cfg,
            label="fine_tuned",
            limit=args.limit,
        )
    else:
        base_path = args.base_eval or (outputs / "eval_base_test_latest.json")
        ft_path = args.ft_eval or (outputs / "eval_fine_tuned_test_latest.json")
        if not base_path.is_file() or not ft_path.is_file():
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "missing eval files; pass --run or provide --base-eval/--ft-eval",
                        "base_path": str(base_path),
                        "ft_path": str(ft_path),
                    }
                )
            )
            return 1
        base_data = json.loads(base_path.read_text(encoding="utf-8"))
        ft_data = json.loads(ft_path.read_text(encoding="utf-8"))
        base_summary = {"model": base_data.get("model"), **(base_data.get("metrics") or {})}
        base_summary["path"] = str(base_path)
        ft_summary = {"model": ft_data.get("model"), **(ft_data.get("metrics") or {})}
        ft_summary["path"] = str(ft_path)

    assert base_summary is not None and ft_summary is not None
    base_m = _metrics_from_eval(base_summary)
    ft_m = _metrics_from_eval(ft_summary)
    deltas = {}
    for k in METRIC_KEYS:
        b = base_m.get(k)
        f = ft_m.get(k)
        if isinstance(b, (int, float)) and isinstance(f, (int, float)):
            deltas[k] = f - b

    comparison = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base": {"model": base_summary.get("model"), "metrics": base_m, "path": base_summary.get("path")},
        "fine_tuned": {
            "model": ft_summary.get("model"),
            "metrics": ft_m,
            "path": ft_summary.get("path"),
        },
        "deltas_ft_minus_base": deltas,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = outputs / f"compare_base_vs_finetuned_{stamp}.json"
    latest = outputs / "compare_base_vs_finetuned_latest.json"
    text = json.dumps(comparison, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(json.dumps({**comparison, "path": str(out), "latest_path": str(latest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
