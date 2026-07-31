#!/usr/bin/env python3
"""Check / poll fine-tuning job until terminal status."""

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
from backend.app.openai_ft.jobs import check_finetuning_job


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll", action="store_true")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--max-wait", type=float, default=7200.0)
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.api_key_configured:
        print(json.dumps({"ok": False, "error": "OPENAI_API_KEY not configured"}))
        return 2

    try:
        result = check_finetuning_job(
            config=cfg,
            poll=args.poll,
            poll_interval_s=args.interval,
            max_wait_s=args.max_wait,
        )
    except MissingAPIKeyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    job = result.get("job") or {}
    public = {
        "ok": result.get("ok"),
        "terminal": result.get("terminal"),
        "timed_out": result.get("timed_out", False),
        "job_id": job.get("id"),
        "status": job.get("status"),
        "fine_tuned_model": job.get("fine_tuned_model"),
        "error": job.get("error"),
        "training_file": job.get("training_file"),
        "validation_file": job.get("validation_file"),
    }
    print(json.dumps(public, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
