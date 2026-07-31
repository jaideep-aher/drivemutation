"""Stage 2 offline evaluation package."""

from backend.app.eval.harness import run_offline_eval
from backend.app.eval.metrics import evaluate_dataset, evaluate_prediction

__all__ = ["evaluate_dataset", "evaluate_prediction", "run_offline_eval"]
