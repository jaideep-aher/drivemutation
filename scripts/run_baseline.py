#!/usr/bin/env python3
"""Evaluate OPENAI_BASE_MODEL on the untouched Stage 2 test set."""

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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

    try:
        summary = evaluate_model_on_split(
            model=cfg.base_model,
            processed_dir=args.processed_dir,
            outputs_dir=args.outputs_dir,
            split=args.split,
            config=cfg,
            label="base",
            limit=args.limit,
        )
    except MissingAPIKeyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2

    # Drop rows from stdout summary
    public = {k: v for k, v in summary.items() if k != "rows"}
    print(json.dumps(public, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
