"""SignalForge FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.signalforge import store
from backend.app.signalforge.export import export_scenario_bundle
from backend.app.signalforge.render import render_scenario
from backend.app.signalforge.schema import (
    CoverageStats,
    GapItem,
    HealthResponse,
    LogicalScenario,
    PointCloudFrame,
    RenderRequest,
    ScenarioSummary,
)

APP_VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(
    title="SignalForge",
    description="Grounded AV scenario generation with synthetic lidar/radar and full provenance",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="SignalForge",
        version=APP_VERSION,
        concrete_count=len(store.load_index()),
        logical_count=len(store.load_catalog()),
    )


@app.get("/api/catalog", response_model=list[LogicalScenario])
def get_catalog() -> list[LogicalScenario]:
    return store.load_catalog()


@app.get("/api/scenarios", response_model=list[ScenarioSummary])
def list_scenarios(
    family: str | None = None,
    weather: str | None = None,
    difficulty: str | None = None,
    lighting: str | None = None,
    q: str | None = None,
    limit: int = Query(80, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ScenarioSummary]:
    return store.list_summaries(
        family=family,
        weather=weather,
        difficulty=difficulty,
        lighting=lighting,
        q=q,
        limit=limit,
        offset=offset,
    )


@app.get("/api/scenarios/count")
def scenarios_count(
    family: str | None = None,
    weather: str | None = None,
    difficulty: str | None = None,
) -> dict:
    all_s = store.list_summaries(
        family=family, weather=weather, difficulty=difficulty, limit=100000
    )
    return {"count": len(all_s)}


@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict:
    sc = store.load_concrete(scenario_id)
    if not sc:
        raise HTTPException(404, f"scenario {scenario_id} not found")
    return sc.model_dump(mode="json")


@app.post("/api/render", response_model=list[PointCloudFrame])
def render(req: RenderRequest) -> list[PointCloudFrame]:
    # Prefer showcase cache for full playback
    cached = store.load_showcase(req.scenario_id)
    if cached and req.frame_idx is None:
        frames = [PointCloudFrame.model_validate(f) for f in cached]
        if req.max_frames < len(frames):
            frames = frames[: req.max_frames]
        return frames

    sc = store.load_concrete(req.scenario_id)
    if not sc:
        raise HTTPException(404, f"scenario {req.scenario_id} not found")

    frames = render_scenario(
        sc,
        max_frames=req.max_frames,
        lidar_beams=req.lidar_beams,
        lidar_azimuth=req.lidar_azimuth,
        degrade=req.degrade,
    )
    if req.frame_idx is not None:
        if req.frame_idx < 0 or req.frame_idx >= len(frames):
            raise HTTPException(400, "frame_idx out of range")
        return [frames[req.frame_idx]]
    return frames


@app.get("/api/showcase")
def list_showcase() -> list[str]:
    path = store.SHOWCASE_DIR / "index.json"
    if not path.exists():
        # Fallback: first N from index across families
        summaries = store.list_summaries(limit=30)
        return [s.id for s in summaries]
    import json

    return json.loads(path.read_text())


@app.get("/api/coverage", response_model=CoverageStats)
def coverage() -> CoverageStats:
    return store.coverage_stats(gap_count=len(store.load_gaps()))


@app.get("/api/gaps", response_model=list[GapItem])
def gaps(limit: int = 50) -> list[GapItem]:
    return store.load_gaps()[:limit]


@app.get("/api/incidents")
def incidents(limit: int = 50) -> list[dict]:
    return store.load_incidents()[:limit]


@app.get("/api/export/{scenario_id}")
def export_scenario(scenario_id: str, max_frames: int = 8) -> dict:
    sc = store.load_concrete(scenario_id)
    if not sc:
        raise HTTPException(404, f"scenario {scenario_id} not found")
    frames = None
    cached = store.load_showcase(scenario_id)
    if cached:
        frames = [PointCloudFrame.model_validate(f) for f in cached[:max_frames]]
    return export_scenario_bundle(sc, frames, max_frames=max_frames)


@app.get("/api/weights")
def weights() -> dict:
    return {
        "sgo_family_weights": store.load_family_weights(),
    }


# Static frontend (production)
if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str = ""):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(404, "frontend not built")
