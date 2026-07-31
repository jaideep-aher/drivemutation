#!/usr/bin/env python3
"""Evaluate a model (base or fine-tuned) on the Stage 2 test set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.openai_ft.client import MissingAPIKeyError
from backend.app.openai_ft.config import load_config
from backend.app.openai_ft.evaluate import evaluate_model_on_split
from backend.app.openai_ft.state import load_state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--which",
        choices=("base", "fine-tuned", "model"),
        default="fine-tuned",
    )
    parser.add_argument("--model", default=None, help="Explicit model id when --which=model")
    parser.add_argument("--label", default=None)
    parser.add_argument("--split", default="test")
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
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.api_key_configured:
        print(json.dumps({"ok": False, "error": "OPENAI_API_KEY not configured"}))
        return 2

    state = load_state(cfg.state_path)
    if args.which == "base":
        model = cfg.base_model
        label = args.label or "base"
    elif args.which == "fine-tuned":
        model = cfg.fine_tuned_model or (state.fine_tuned_model or "")
        label = args.label or "fine_tuned"
        if not model:
            print(json.dumps({"ok": False, "error": "OPENAI_FINE_TUNED_MODEL not set"}))
            return 2
    else:
        if not args.model:
            print(json.dumps({"ok": False, "error": "--model required when --which=model"}))
            return 2
        model = args.model
        label = args.label or "custom"

    try:
        summary = evaluate_model_on_split(
            model=model,
            processed_dir=args.processed_dir,
            outputs_dir=args.outputs_dir,
            split=args.split,
            config=cfg,
            label=label,
            limit=args.limit,
        )
    except MissingAPIKeyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    public = {k: v for k, v in summary.items() if k != "rows"}
    print(json.dumps(public, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
