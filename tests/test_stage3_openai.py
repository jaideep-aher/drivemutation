"""Stage 3 OpenAI fine-tuning / compile tests (mocked SDK  -  no real API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.dataset.schemas import SYSTEM_PROMPT, MutationTarget, RejectionTarget
from backend.app.main import app
from backend.app.openai_ft.compile import compile_scenario
from backend.app.openai_ft.config import Stage3Config, update_env_keys
from backend.app.openai_ft.evaluate import evaluate_model_on_split
from backend.app.openai_ft.jobs import (
    check_finetuning_job,
    create_or_resume_finetuning_job,
    models_status,
    upload_training_files,
)
from backend.app.openai_ft.sft_format import write_openai_finetune_jsonl
from backend.app.openai_ft.state import FineTuneState, load_state, save_state
from backend.app.presets import get_preset

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def _cfg(tmp_path: Path, **kwargs: Any) -> Stage3Config:
    state_path = tmp_path / ".openai_ft_state.json"
    base = dict(
        api_key="sk-test-not-real",
        base_model="gpt-4o-mini-2024-07-18",
        fine_tuning_job_id="",
        fine_tuned_model="",
        root=ROOT,
        state_path=state_path,
        env_paths=[tmp_path / ".env.local"],
        sync_env=False,
    )
    base.update(kwargs)
    return Stage3Config(**base)


def _chat_response(content: str, *, prompt: int = 10, completion: int = 20) -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


@pytest.fixture
def accepted_json() -> str:
    preset = get_preset("occluded_pedestrian")
    # Minimal accepted target mirroring dataset schema
    target = {
        "status": "accepted",
        "mutation": {
            "operations": [
                {
                    "op": "set_actor_behavior",
                    "actor_id": "ped",
                    "behavior": {
                        "type": "triggered_crossing",
                        "trigger_id": "t_cross",
                        "post_trigger_velocity": {"vx": 0.0, "vy": 1.5},
                    },
                }
            ]
        },
        "activated_hazard": "occluded_crossing_ped",
        "scenario_family": "occluded_pedestrian",
    }
    # Use gold from a real example if available
    test_path = ROOT / "data" / "processed" / "test.jsonl"
    if test_path.is_file():
        for line in test_path.read_text(encoding="utf-8").splitlines():
            ex = json.loads(line)
            if ex["target_kind"] == "mutation":
                return ex["messages"][2]["content"]
    return json.dumps(target)


def test_sft_format_extracts_messages_only(tmp_path: Path):
    src = tmp_path / "train.jsonl"
    src.write_text(
        json.dumps(
            {
                "id": "x",
                "messages": [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "{\"status\":\"rejected\",\"reasons\":[{\"code\":\"c\",\"message\":\"m\"}]}"},
                ],
                "extra": "ignore",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / "openai.jsonl"
    meta = write_openai_finetune_jsonl(src, dest)
    assert meta["n"] == 1
    row = json.loads(dest.read_text(encoding="utf-8").strip())
    assert set(row.keys()) == {"messages"}
    assert [m["role"] for m in row["messages"]] == ["system", "user", "assistant"]


def test_state_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    state = FineTuneState(training_file_id="file-train", validation_file_id="file-val")
    save_state(state, path)
    loaded = load_state(path)
    assert loaded.training_file_id == "file-train"
    assert loaded.validation_file_id == "file-val"


def test_upload_and_create_job_idempotent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    # Prepare tiny processed files
    processed = tmp_path / "processed"
    processed.mkdir()
    row = {
        "id": "e1",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "goal"},
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "status": "rejected",
                        "reasons": [{"code": "impossible", "message": "no"}],
                    }
                ),
            },
        ],
    }
    for name in ("train", "validation"):
        (processed / f"{name}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    mock_cli = MagicMock()
    mock_cli.files.create.side_effect = [
        SimpleNamespace(id="file-train-1"),
        SimpleNamespace(id="file-val-1"),
    ]
    staging = tmp_path / "staging"
    state = upload_training_files(
        processed_dir=processed,
        staging_dir=staging,
        client=mock_cli,
        config=cfg,
    )
    assert state.training_file_id == "file-train-1"
    assert mock_cli.files.create.call_count == 2

    # Second upload should be no-op
    state2 = upload_training_files(
        processed_dir=processed,
        staging_dir=staging,
        client=mock_cli,
        config=cfg,
    )
    assert state2.training_file_id == "file-train-1"
    assert mock_cli.files.create.call_count == 2

    mock_cli.fine_tuning.jobs.list.return_value = []
    mock_cli.fine_tuning.jobs.create.return_value = SimpleNamespace(
        id="ftjob-1",
        status="validating_files",
        model=cfg.base_model,
        fine_tuned_model=None,
        training_file="file-train-1",
        validation_file="file-val-1",
        error=None,
        created_at=1,
        finished_at=None,
    )
    created = create_or_resume_finetuning_job(client=mock_cli, config=cfg)
    assert created["created"] is True
    assert created["job"]["id"] == "ftjob-1"

    # Resume should not create again
    mock_cli.fine_tuning.jobs.retrieve.return_value = SimpleNamespace(
        id="ftjob-1",
        status="running",
        model=cfg.base_model,
        fine_tuned_model=None,
        training_file="file-train-1",
        validation_file="file-val-1",
        error=None,
        created_at=1,
        finished_at=None,
    )
    cfg2 = _cfg(tmp_path, fine_tuning_job_id="ftjob-1")
    resumed = create_or_resume_finetuning_job(client=mock_cli, config=cfg2)
    assert resumed["created"] is False
    assert resumed["resumed"] is True
    mock_cli.fine_tuning.jobs.create.assert_called_once()


def test_check_job_records_failure(tmp_path: Path):
    cfg = _cfg(tmp_path, fine_tuning_job_id="ftjob-fail")
    save_state(FineTuneState(fine_tuning_job_id="ftjob-fail"), cfg.state_path)
    mock_cli = MagicMock()
    mock_cli.fine_tuning.jobs.retrieve.return_value = SimpleNamespace(
        id="ftjob-fail",
        status="failed",
        model=cfg.base_model,
        fine_tuned_model=None,
        training_file="file-a",
        validation_file="file-b",
        error=SimpleNamespace(message="invalid training file"),
        created_at=1,
        finished_at=2,
    )
    mock_cli.fine_tuning.jobs.list_events.return_value = [
        SimpleNamespace(created_at=1, level="error", message="bad row")
    ]
    result = check_finetuning_job(client=mock_cli, config=cfg, poll=False)
    assert result["job"]["status"] == "failed"
    assert "invalid" in (result["job"]["error"] or "")
    state = load_state(cfg.state_path)
    assert state.status == "failed"
    assert state.extra.get("recent_events")


def test_compile_rejects_malformed_json_no_simulate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = _cfg(tmp_path)
    mock_cli = MagicMock()
    mock_cli.chat.completions.create.return_value = _chat_response("not-json{{{")
    seed = get_preset("wrong_way_vehicle")
    out = compile_scenario(
        seed_scene=seed,
        testing_goal="make it worse",
        mode="base",
        client=mock_cli,
        config=cfg,
    )
    assert out["ok"] is False
    assert out["error_code"] == "malformed_json"
    assert out["simulation"] is None


def test_compile_rejects_schema_invalid(tmp_path: Path):
    cfg = _cfg(tmp_path)
    mock_cli = MagicMock()
    mock_cli.chat.completions.create.return_value = _chat_response(
        json.dumps({"status": "accepted", "mutation": {"operations": []}})
    )
    seed = get_preset("wrong_way_vehicle")
    out = compile_scenario(
        seed_scene=seed,
        testing_goal="x",
        mode="base",
        client=mock_cli,
        config=cfg,
    )
    assert out["json_parse_ok"] is True
    assert out["schema_valid"] is False
    assert out["error_code"] == "schema_invalid"
    assert out["simulation"] is None


def test_compile_accepted_gold_runs_simulation(tmp_path: Path, accepted_json: str):
    cfg = _cfg(tmp_path)
    mock_cli = MagicMock()
    mock_cli.chat.completions.create.return_value = _chat_response(accepted_json)
    # Use matching seed from the example if possible
    test_path = ROOT / "data" / "processed" / "test.jsonl"
    seed = get_preset("occluded_pedestrian")
    goal = "test"
    if test_path.is_file():
        for line in test_path.read_text(encoding="utf-8").splitlines():
            ex = json.loads(line)
            if ex["messages"][2]["content"] == accepted_json:
                from backend.app.schemas.scenario import ScenarioSpec

                seed = ScenarioSpec.model_validate(ex["seed_scene"])
                goal = ex["testing_goal"]
                break
    out = compile_scenario(
        seed_scene=seed,
        testing_goal=goal,
        mode="base",
        client=mock_cli,
        config=cfg,
    )
    assert out["json_parse_ok"] is True
    assert out["schema_valid"] is True
    # Gold dataset examples are physically valid
    assert out["physical_valid"] is True
    assert out["ok"] is True
    assert out["simulation"] is not None
    assert out["simulation"]["valid"] is True


def test_compile_missing_ft_model(tmp_path: Path):
    cfg = _cfg(tmp_path, api_key="sk-test", fine_tuned_model="")
    seed = get_preset("wrong_way_vehicle")
    out = compile_scenario(
        seed_scene=seed,
        testing_goal="x",
        mode="fine-tuned",
        client=MagicMock(),
        config=cfg,
    )
    assert out["error_code"] == "missing_model_config"


def test_evaluate_model_mocked(tmp_path: Path, accepted_json: str):
    cfg = _cfg(tmp_path)
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir()
    # One gold mutation example rewritten with assistant content
    test_path = ROOT / "data" / "processed" / "test.jsonl"
    lines = test_path.read_text(encoding="utf-8").splitlines()[:2]
    (processed / "test.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    mock_cli = MagicMock()

    def _side_effect(**kwargs: Any) -> Any:
        # Return gold assistant from the matching example when possible
        # Fall back to accepted_json
        return _chat_response(accepted_json)

    mock_cli.chat.completions.create.side_effect = _side_effect
    summary = evaluate_model_on_split(
        model=cfg.base_model,
        processed_dir=processed,
        outputs_dir=outputs,
        split="test",
        client=mock_cli,
        config=cfg,
        label="base",
    )
    assert summary["n"] == 2
    assert "json_parse_rate" in summary
    assert Path(summary["path"]).is_file()
    assert "latency" in summary
    assert "token_use" in summary


def test_api_models_status_no_secret_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Point state to temp; monkeypatch load_config via env absence of real key exposure
    r = client.get("/api/models/status")
    assert r.status_code == 200
    body = r.json()
    assert "api_key" not in body
    assert "api_key_configured" in body
    dumped = json.dumps(body)
    assert "sk-" not in dumped


def test_api_compile_base_mocked(monkeypatch: pytest.MonkeyPatch, accepted_json: str):
    def fake_compile(**kwargs: Any) -> dict[str, Any]:
        return {
            "mode": "base",
            "model": "gpt-4o-mini-2024-07-18",
            "ok": True,
            "error_code": None,
            "error": None,
            "target_kind": "mutation",
            "json_parse_ok": True,
            "schema_valid": True,
            "physical_valid": True,
            "parsed": json.loads(accepted_json),
            "validation_issues": [],
            "simulation": None,
            "latency_s": 0.1,
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }

    monkeypatch.setattr("backend.app.main.compile_scenario", fake_compile)
    seed = get_preset("wrong_way_vehicle")
    r = client.post(
        "/api/compile/base",
        json={"seed_scene": seed.model_dump(mode="json"), "testing_goal": "stress test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "base"
    assert "sk-" not in json.dumps(body)


def test_api_compile_fine_tuned_pending(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.app.main.models_status",
        lambda config=None: {
            "job_pending": True,
            "fine_tuning_status": "running",
            "job_failed": False,
        },
    )
    seed = get_preset("wrong_way_vehicle")
    r = client.post(
        "/api/compile/fine-tuned",
        json={"seed_scene": seed.model_dump(mode="json"), "testing_goal": "x"},
    )
    assert r.status_code == 200
    assert r.json()["error_code"] == "fine_tuning_pending"


def test_api_evaluation_summary():
    r = client.get("/api/evaluation/summary")
    assert r.status_code == 200
    body = r.json()
    assert "base" in body
    assert "fine_tuned" in body
    assert "available" in body
    assert "methodology" in body
    assert body["methodology"]["temperature"] == 0.0


def test_update_env_keys_merges(tmp_path: Path):
    path = tmp_path / ".env.local"
    path.write_text("OPENAI_API_KEY=sk-keep\nOTHER=1\n", encoding="utf-8")
    update_env_keys(
        {"OPENAI_FINE_TUNING_JOB_ID": "ftjob-x", "OPENAI_FINE_TUNED_MODEL": "ft:model"},
        paths=[path],
    )
    text = path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-keep" in text
    assert "OTHER=1" in text
    assert "OPENAI_FINE_TUNING_JOB_ID=ftjob-x" in text
    assert "OPENAI_FINE_TUNED_MODEL=ft:model" in text


def test_stage1_health_still_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
