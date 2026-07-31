"""Load Stage 3 configuration from local env files (never expose secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE_MODEL = "gpt-4o-mini-2024-07-18"
STATE_PATH = ROOT / "data" / "outputs" / ".openai_ft_state.json"
EVAL_TEMPERATURE = 0.0
EVAL_MAX_TOKENS = 2048
REQUEST_TIMEOUT_S = 60.0


def redact_secret(value: str | None, *, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}…{value[-keep:]}"


def _merge_env_files() -> dict[str, str]:
    """Prefer .env.local over .env over process env for known keys."""
    merged: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local"):
        if not path.is_file():
            continue
        values = dotenv_values(path)
        for k, v in values.items():
            if v is None:
                continue
            merged[k] = v
    # Process env can override for CI/tests if explicitly set
    for key in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_MODEL",
        "OPENAI_FINE_TUNING_JOB_ID",
        "OPENAI_FINE_TUNED_MODEL",
        "OPENAI_ORG_ID",
    ):
        if key in os.environ and os.environ[key] != "":
            merged[key] = os.environ[key]
    return merged


@dataclass
class Stage3Config:
    api_key: str
    base_model: str
    fine_tuning_job_id: str
    fine_tuned_model: str
    root: Path = ROOT
    state_path: Path = STATE_PATH
    env_paths: list[Path] | None = None
    sync_env: bool = True

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def fine_tuned_configured(self) -> bool:
        return bool(self.fine_tuned_model.strip())

    def resolved_env_paths(self) -> list[Path]:
        if self.env_paths is not None:
            return self.env_paths
        return [ROOT / ".env.local", ROOT / ".env"]

    def public_dict(self) -> dict[str, object]:
        return {
            "api_key_configured": self.api_key_configured,
            "base_model": self.base_model,
            "fine_tuning_job_id": self.fine_tuning_job_id or None,
            "fine_tuned_model": self.fine_tuned_model or None,
        }


def load_config() -> Stage3Config:
    env = _merge_env_files()
    return Stage3Config(
        api_key=env.get("OPENAI_API_KEY", "").strip(),
        base_model=env.get("OPENAI_BASE_MODEL", DEFAULT_BASE_MODEL).strip()
        or DEFAULT_BASE_MODEL,
        fine_tuning_job_id=env.get("OPENAI_FINE_TUNING_JOB_ID", "").strip(),
        fine_tuned_model=env.get("OPENAI_FINE_TUNED_MODEL", "").strip(),
    )


def update_env_keys(updates: dict[str, str], *, paths: list[Path] | None = None) -> None:
    """Merge non-secret and secret keys into env files without wiping others.

    Never prints values. Only writes provided keys.
    """
    targets = paths or [ROOT / ".env.local", ROOT / ".env"]
    for path in targets:
        existing: dict[str, str] = {}
        order: list[str] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                if k not in existing:
                    order.append(k)
                existing[k] = v
        for k, v in updates.items():
            if k not in existing:
                order.append(k)
            existing[k] = v
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(f"{k}={existing[k]}" for k in order) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
