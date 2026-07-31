"""OpenAI client factory — API key never returned to callers beyond the SDK client."""

from __future__ import annotations

from openai import OpenAI

from backend.app.openai_ft.config import REQUEST_TIMEOUT_S, Stage3Config, load_config


class MissingAPIKeyError(RuntimeError):
    """Raised when OPENAI_API_KEY is not configured."""


def get_client(config: Stage3Config | None = None) -> OpenAI:
    cfg = config or load_config()
    if not cfg.api_key_configured:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY is missing or empty in .env.local / .env"
        )
    return OpenAI(api_key=cfg.api_key, timeout=REQUEST_TIMEOUT_S)
