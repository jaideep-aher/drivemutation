#!/usr/bin/env python3
"""Upload train/validation JSONL to OpenAI with purpose=fine-tune."""

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
from backend.app.openai_ft.jobs import upload_training_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=ROOT / "data" / "processed",
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=ROOT / "data" / "outputs" / "openai_staging",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.api_key_configured:
        print(json.dumps({"ok": False, "error": "OPENAI_API_KEY not configured"}))
        return 2

    try:
        state = upload_training_files(
            processed_dir=args.processed_dir,
            staging_dir=args.staging_dir,
            config=cfg,
            force=args.force,
        )
    except MissingAPIKeyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "training_file_id": state.training_file_id,
                "validation_file_id": state.validation_file_id,
                "status": state.status,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
