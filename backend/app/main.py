"""DriveMutation FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.openai_ft.compile import compile_scenario
from backend.app.openai_ft.config import ROOT, load_config
from backend.app.openai_ft.evaluate import load_latest_eval_summary
from backend.app.openai_ft.jobs import models_status
from backend.app.presets import get_preset, list_presets
from backend.app.schemas.scenario import (
    CompileRequest,
    CompileResponse,
    HealthResponse,
    PresetSummary,
    ScenarioSpec,
    SimulateRequest,
    SimulateResponse,
    ValidateRequest,
    ValidateResponse,
    ValidationIssue,
)
from backend.app.simulator import simulate
from backend.app.validators import validate_scenario

APP_VERSION = "0.4.0"
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(
    title="DriveMutation",
    description="Local counterfactual AV test compiler - base vs fine-tuned demo",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _compile_response(raw: dict) -> CompileResponse:
    issues = [
        ValidationIssue.model_validate(i) if isinstance(i, dict) else i
        for i in (raw.get("validation_issues") or [])
    ]
    sim = None
    if raw.get("simulation"):
        sim = SimulateResponse.model_validate(raw["simulation"])
    return CompileResponse(
        mode=raw.get("mode") or "",
        model=raw.get("model"),
        ok=bool(raw.get("ok")),
        error_code=raw.get("error_code"),
        error=raw.get("error"),
        target_kind=raw.get("target_kind"),
        json_parse_ok=bool(raw.get("json_parse_ok")),
        schema_valid=bool(raw.get("schema_valid")),
        physical_valid=bool(raw.get("physical_valid")),
        parsed=raw.get("parsed"),
        validation_issues=issues,
        simulation=sim,
        latency_s=raw.get("latency_s"),
        usage=raw.get("usage"),
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="DriveMutation",
        version=APP_VERSION,
        deterministic=True,
    )


@app.post("/api/validate", response_model=ValidateResponse)
def api_validate(body: ValidateRequest) -> ValidateResponse:
    issues = validate_scenario(body.scenario)
    return ValidateResponse(valid=len(issues) == 0, issues=issues)


@app.post("/api/simulate", response_model=SimulateResponse)
def api_simulate(body: SimulateRequest) -> SimulateResponse:
    issues = validate_scenario(body.scenario)
    if issues:
        return SimulateResponse(
            scenario_id=body.scenario.id,
            valid=False,
            validation_issues=issues,
        )
    return simulate(body.scenario)


@app.get("/api/presets", response_model=list[PresetSummary])
def api_presets() -> list[PresetSummary]:
    return list_presets()


@app.get("/api/presets/{preset_id}", response_model=ScenarioSpec)
def api_preset_detail(preset_id: str) -> ScenarioSpec:
    try:
        return get_preset(preset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown preset: {preset_id}") from exc


@app.post("/api/compile/base", response_model=CompileResponse)
def api_compile_base(body: CompileRequest) -> CompileResponse:
    raw = compile_scenario(
        seed_scene=body.seed_scene,
        testing_goal=body.testing_goal,
        mode="base",
        run_simulation=body.run_simulation,
    )
    # Never leak API key material
    if raw.get("error") and "sk-" in str(raw.get("error")):
        raw["error"] = "api_error (details redacted)"
    return _compile_response(raw)


@app.post("/api/compile/fine-tuned", response_model=CompileResponse)
def api_compile_fine_tuned(body: CompileRequest) -> CompileResponse:
    cfg = load_config()
    status = models_status(config=cfg)
    if status.get("job_pending"):
        return _compile_response(
            {
                "mode": "fine-tuned",
                "model": None,
                "ok": False,
                "error_code": "fine_tuning_pending",
                "error": f"fine-tuning job status={status.get('fine_tuning_status')}",
                "json_parse_ok": False,
                "schema_valid": False,
                "physical_valid": False,
                "validation_issues": [],
            }
        )
    if status.get("job_failed"):
        return _compile_response(
            {
                "mode": "fine-tuned",
                "model": None,
                "ok": False,
                "error_code": "fine_tuning_failed",
                "error": status.get("fine_tuning_error") or "fine-tuning job failed",
                "json_parse_ok": False,
                "schema_valid": False,
                "physical_valid": False,
                "validation_issues": [],
            }
        )
    raw = compile_scenario(
        seed_scene=body.seed_scene,
        testing_goal=body.testing_goal,
        mode="fine-tuned",
        run_simulation=body.run_simulation,
    )
    if raw.get("error") and "sk-" in str(raw.get("error")):
        raw["error"] = "api_error (details redacted)"
    return _compile_response(raw)


@app.get("/api/models/status")
def api_models_status() -> dict:
    status = models_status()
    # Ensure no secret fields
    status.pop("api_key", None)
    return status


@app.get("/api/evaluation/summary")
def api_evaluation_summary() -> dict:
    outputs = Path(ROOT) / "data" / "outputs"
    return load_latest_eval_summary(outputs)


if FRONTEND_DIST.is_dir():
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # Keep API routes ahead of this catch-all.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
