"""Persist fine-tuning file/job IDs in an untracked local state file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.openai_ft.config import STATE_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FineTuneState:
    training_file_id: str | None = None
    validation_file_id: str | None = None
    fine_tuning_job_id: str | None = None
    fine_tuned_model: str | None = None
    base_model: str | None = None
    status: str | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    training_filename: str | None = None
    validation_filename: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FineTuneState:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)


def load_state(path: Path | None = None) -> FineTuneState:
    p = path or STATE_PATH
    if not p.is_file():
        return FineTuneState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return FineTuneState()
    if not isinstance(data, dict):
        return FineTuneState()
    return FineTuneState.from_dict(data)


def save_state(state: FineTuneState, path: Path | None = None) -> Path:
    p = path or STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _now()
    if not state.created_at:
        state.created_at = state.updated_at
    p.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return p
