"""Idempotent OpenAI fine-tuning job helpers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from backend.app.openai_ft.client import get_client
from backend.app.openai_ft.config import (
    DEFAULT_BASE_MODEL,
    Stage3Config,
    load_config,
    update_env_keys,
)
from backend.app.openai_ft.sft_format import write_openai_finetune_jsonl
from backend.app.openai_ft.state import FineTuneState, load_state, save_state

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
ACTIVE_STATUSES = {"validating_files", "queued", "running"}


def _job_public(job: Any) -> dict[str, Any]:
    err = getattr(job, "error", None)
    error_msg = None
    if err is not None:
        error_msg = getattr(err, "message", None)
        if not error_msg:
            # SDK may return an empty Error object  -  treat as no error
            code = getattr(err, "code", None)
            if code:
                error_msg = str(err)
            else:
                error_msg = None
    return {
        "id": getattr(job, "id", None),
        "status": getattr(job, "status", None),
        "model": getattr(job, "model", None),
        "fine_tuned_model": getattr(job, "fine_tuned_model", None),
        "training_file": getattr(job, "training_file", None),
        "validation_file": getattr(job, "validation_file", None),
        "error": error_msg,
        "created_at": getattr(job, "created_at", None),
        "finished_at": getattr(job, "finished_at", None),
    }


def upload_training_files(
    *,
    processed_dir: Path,
    staging_dir: Path,
    client: OpenAI | None = None,
    config: Stage3Config | None = None,
    force: bool = False,
) -> FineTuneState:
    """Convert + upload train/validation JSONL (purpose=fine-tune). Idempotent via state."""
    cfg = config or load_config()
    cli = client or get_client(cfg)
    state = load_state(cfg.state_path)

    if (
        not force
        and state.training_file_id
        and state.validation_file_id
        and state.fine_tuning_job_id
    ):
        # Already uploaded for an existing job  -  keep IDs
        return state

    if not force and state.training_file_id and state.validation_file_id:
        return state

    staging_dir.mkdir(parents=True, exist_ok=True)
    train_src = processed_dir / "train.jsonl"
    val_src = processed_dir / "validation.jsonl"
    train_ft = staging_dir / "openai_train.jsonl"
    val_ft = staging_dir / "openai_validation.jsonl"
    write_openai_finetune_jsonl(train_src, train_ft)
    write_openai_finetune_jsonl(val_src, val_ft)

    train_file = cli.files.create(file=train_ft, purpose="fine-tune")
    val_file = cli.files.create(file=val_ft, purpose="fine-tune")

    state.training_file_id = train_file.id
    state.validation_file_id = val_file.id
    state.training_filename = train_ft.name
    state.validation_filename = val_ft.name
    state.base_model = cfg.base_model or DEFAULT_BASE_MODEL
    state.status = "files_uploaded"
    state.error = None
    save_state(state, cfg.state_path)
    return state


def create_or_resume_finetuning_job(
    *,
    client: OpenAI | None = None,
    config: Stage3Config | None = None,
    suffix: str = "drivemutation",
    force_new: bool = False,
) -> dict[str, Any]:
    """Create SFT job only if none exists; otherwise resume monitoring existing."""
    cfg = config or load_config()
    cli = client or get_client(cfg)
    state = load_state(cfg.state_path)

    # Prefer env job id, then state
    job_id = cfg.fine_tuning_job_id or state.fine_tuning_job_id
    if job_id and not force_new:
        try:
            job = cli.fine_tuning.jobs.retrieve(job_id)
        except Exception as exc:  # noqa: BLE001
            # Stale / invalid job id  -  clear and fall through to create
            msg = str(exc)
            if "not_found" in msg or "Could not find" in msg or "404" in msg:
                state.fine_tuning_job_id = None
                cfg.fine_tuning_job_id = ""
                state.error = f"cleared_stale_job_id:{job_id}"
                save_state(state, cfg.state_path)
                job_id = None
            else:
                raise
        if job_id:
            pub = _job_public(job)
            state.fine_tuning_job_id = pub["id"]
            state.status = pub["status"]
            state.fine_tuned_model = pub["fine_tuned_model"] or state.fine_tuned_model
            state.error = pub["error"]
            if pub["training_file"]:
                state.training_file_id = pub["training_file"]
            if pub["validation_file"]:
                state.validation_file_id = pub["validation_file"]
            save_state(state, cfg.state_path)
            _sync_env_from_state(state, cfg)
            return {"created": False, "resumed": True, "job": pub, "state": state.to_dict()}

    if not state.training_file_id or not state.validation_file_id:
        raise RuntimeError(
            "training/validation file IDs missing  -  run upload_training_data first"
        )

    # Search recent jobs for same training file to avoid duplicate paid jobs
    for existing in cli.fine_tuning.jobs.list(limit=20):
        if (
            existing.training_file == state.training_file_id
            and existing.model == (state.base_model or cfg.base_model)
            and existing.status in ACTIVE_STATUSES | {"succeeded"}
        ):
            pub = _job_public(existing)
            state.fine_tuning_job_id = pub["id"]
            state.status = pub["status"]
            state.fine_tuned_model = pub["fine_tuned_model"] or state.fine_tuned_model
            state.error = pub["error"]
            save_state(state, cfg.state_path)
            _sync_env_from_state(state, cfg)
            return {
                "created": False,
                "resumed": True,
                "matched_existing": True,
                "job": pub,
                "state": state.to_dict(),
            }

    job = cli.fine_tuning.jobs.create(
        training_file=state.training_file_id,
        validation_file=state.validation_file_id,
        model=state.base_model or cfg.base_model or DEFAULT_BASE_MODEL,
        suffix=suffix,
    )
    pub = _job_public(job)
    state.fine_tuning_job_id = pub["id"]
    state.status = pub["status"]
    state.fine_tuned_model = pub["fine_tuned_model"]
    state.error = pub["error"]
    state.base_model = pub["model"] or state.base_model
    save_state(state, cfg.state_path)
    _sync_env_from_state(state, cfg)
    return {"created": True, "resumed": False, "job": pub, "state": state.to_dict()}


def check_finetuning_job(
    *,
    client: OpenAI | None = None,
    config: Stage3Config | None = None,
    poll: bool = False,
    poll_interval_s: float = 30.0,
    max_wait_s: float = 3600.0,
) -> dict[str, Any]:
    cfg = config or load_config()
    cli = client or get_client(cfg)
    state = load_state(cfg.state_path)
    job_id = cfg.fine_tuning_job_id or state.fine_tuning_job_id
    if not job_id:
        return {
            "ok": False,
            "error": "no fine-tuning job id in state or env",
            "state": state.to_dict(),
        }

    started = time.time()
    while True:
        job = cli.fine_tuning.jobs.retrieve(job_id)
        pub = _job_public(job)
        state.fine_tuning_job_id = pub["id"]
        state.status = pub["status"]
        state.fine_tuned_model = pub["fine_tuned_model"] or state.fine_tuned_model
        state.error = pub["error"]
        if pub["status"] == "failed":
            # Capture recent events for diagnostics (no secrets)
            try:
                events = list(cli.fine_tuning.jobs.list_events(job_id, limit=10))
                state.extra["recent_events"] = [
                    {
                        "created_at": getattr(e, "created_at", None),
                        "level": getattr(e, "level", None),
                        "message": getattr(e, "message", None),
                    }
                    for e in events
                ]
            except Exception as exc:  # noqa: BLE001
                state.extra["events_error"] = str(exc)
        save_state(state, cfg.state_path)
        _sync_env_from_state(state, cfg)

        if pub["status"] in TERMINAL_STATUSES or not poll:
            return {"ok": True, "job": pub, "state": state.to_dict(), "terminal": pub["status"] in TERMINAL_STATUSES}

        if time.time() - started >= max_wait_s:
            return {
                "ok": True,
                "job": pub,
                "state": state.to_dict(),
                "terminal": False,
                "timed_out": True,
            }
        time.sleep(poll_interval_s)


def _sync_env_from_state(state: FineTuneState, config: Stage3Config | None = None) -> None:
    cfg = config or load_config()
    if not cfg.sync_env:
        return
    updates: dict[str, str] = {}
    if state.fine_tuning_job_id:
        updates["OPENAI_FINE_TUNING_JOB_ID"] = state.fine_tuning_job_id
    if state.fine_tuned_model:
        updates["OPENAI_FINE_TUNED_MODEL"] = state.fine_tuned_model
    if updates:
        update_env_keys(updates, paths=cfg.resolved_env_paths())


def models_status(*, config: Stage3Config | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    state = load_state(cfg.state_path)
    job_id = cfg.fine_tuning_job_id or state.fine_tuning_job_id
    ft_model = cfg.fine_tuned_model or state.fine_tuned_model
    status = state.status
    error = state.error

    # Optionally refresh from API if key present
    live = None
    if cfg.api_key_configured and job_id:
        try:
            cli = get_client(cfg)
            job = cli.fine_tuning.jobs.retrieve(job_id)
            live = _job_public(job)
            status = live["status"]
            ft_model = live["fine_tuned_model"] or ft_model
            error = live["error"]
            state.status = status
            state.fine_tuned_model = ft_model
            state.error = error
            save_state(state, cfg.state_path)
            _sync_env_from_state(state, cfg)
        except Exception as exc:  # noqa: BLE001
            live = {"error": str(exc)}

    return {
        "api_key_configured": cfg.api_key_configured,
        "base_model": cfg.base_model,
        "fine_tuned_model": ft_model or None,
        "fine_tuning_job_id": job_id or None,
        "fine_tuning_status": status,
        "fine_tuning_error": error,
        "training_file_id": state.training_file_id,
        "validation_file_id": state.validation_file_id,
        "live": live,
        "base_ready": bool(cfg.base_model),
        "fine_tuned_ready": bool(ft_model) and status == "succeeded",
        "job_pending": status in ACTIVE_STATUSES if status else False,
        "job_failed": status == "failed",
    }
