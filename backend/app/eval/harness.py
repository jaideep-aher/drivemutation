"""Offline evaluation harness for Stage 2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.dataset.validate_dataset import load_jsonl
from backend.app.eval.metrics import evaluate_dataset


def run_offline_eval(
    processed_dir: Path,
    outputs_dir: Path,
    *,
    split: str = "test",
    predictions_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate gold (or provided) predictions on a split and write a report."""
    path = processed_dir / f"{split}.jsonl"
    examples = load_jsonl(path)
    predictions = None
    if predictions_path is not None and predictions_path.is_file():
        raw = json.loads(predictions_path.read_text(encoding="utf-8"))
        predictions = {k: v for k, v in raw.items()}

    report = evaluate_dataset(examples, predictions=predictions)
    summary = {k: v for k, v in report.items() if k != "rows"}
    summary["split"] = split
    summary["n_rows"] = report["n"]
    outputs_dir.mkdir(parents=True, exist_ok=True)
    out = outputs_dir / f"eval_{split}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["path"] = str(out)
    return summary
