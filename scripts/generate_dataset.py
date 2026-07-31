#!/usr/bin/env python3
"""Regenerate the Stage 2 supervised fine-tuning dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.dataset.compositions import DEFAULT_SEED
from backend.app.dataset.generate import generate_and_write


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
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
    summary = generate_and_write(args.processed_dir, args.outputs_dir, seed=args.seed)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"validation"}}, indent=2))
    print("validation_ok=", summary["validation"]["ok"])
    print("train_test_leakage=", summary["leakage"]["has_train_test_leakage"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
