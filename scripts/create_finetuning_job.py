#!/usr/bin/env python3
"""Create supervised fine-tuning job (idempotent  -  never duplicates paid jobs)."""

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
from backend.app.openai_ft.jobs import create_or_resume_finetuning_job


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suffix", default="drivemutation")
    parser.add_argument(
        "--force-new",
        action="store_true",
        help="Dangerous: create a new job even if one exists (default: resume)",
    )
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.api_key_configured:
        print(json.dumps({"ok": False, "error": "OPENAI_API_KEY not configured"}))
        return 2

    try:
        result = create_or_resume_finetuning_job(
            config=cfg,
            suffix=args.suffix,
            force_new=args.force_new,
        )
    except MissingAPIKeyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({"ok": True, **{k: v for k, v in result.items() if k != "state"}}, indent=2))
    # Also print job id clearly
    job = result.get("job") or {}
    print(f"job_id={job.get('id')} status={job.get('status')} created={result.get('created')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
