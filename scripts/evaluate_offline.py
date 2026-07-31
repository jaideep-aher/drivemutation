#!/usr/bin/env python3
"""Run offline Stage 2 evaluation on a dataset split (defaults to gold assistants)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.eval.harness import run_offline_eval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="test", choices=["train", "validation", "test"])
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--outputs-dir", type=Path, default=ROOT / "data" / "outputs")
    parser.add_argument("--predictions", type=Path, default=None)
    args = parser.parse_args()
    summary = run_offline_eval(
        args.processed_dir,
        args.outputs_dir,
        split=args.split,
        predictions_path=args.predictions,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
