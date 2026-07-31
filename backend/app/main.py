"""DriveMutation FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.presets import get_preset, list_presets
from backend.app.schemas.scenario import (
    HealthResponse,
    PresetSummary,
    ScenarioSpec,
    SimulateRequest,
    SimulateResponse,
    ValidateRequest,
    ValidateResponse,
)
from backend.app.simulator import simulate
from backend.app.validators import validate_scenario

APP_VERSION = "0.1.0"

app = FastAPI(
    title="DriveMutation",
    description="Local counterfactual AV test compiler — Stage 1 (deterministic)",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
