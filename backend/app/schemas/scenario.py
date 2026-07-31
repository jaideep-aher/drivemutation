"""Complete scenario and request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .actors import (
    Actor,
    CyclistActor,
    EgoVehicle,
    PedestrianActor,
    VehicleActor,
)
from .common import Assumption, NonNegFloat, PositiveFloat, StrictModel, Unknown
from .mutations import MutationSpec
from .oracles import OracleResult, SafetyOracle
from .road import RoadLayout
from .triggers import Trigger


class ScenarioSpec(StrictModel):
    """Complete Stage-1 scenario specification (SI units, deterministic)."""

    id: str
    name: str
    description: str = ""
    duration_s: PositiveFloat = Field(..., description="Simulation horizon [s]")
    timestep_s: PositiveFloat = Field(
        default=0.1, description="Fixed integration step [s]; must be 0.1 for Stage 1"
    )
    road: RoadLayout
    ego: EgoVehicle
    actors: list[VehicleActor | CyclistActor | PedestrianActor] = Field(
        default_factory=list
    )
    triggers: list[Trigger] = Field(default_factory=list)
    oracles: list[SafetyOracle] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)
    mutation: MutationSpec | None = None

    @model_validator(mode="after")
    def _check_timestep(self) -> ScenarioSpec:
        if abs(self.timestep_s - 0.1) > 1e-12:
            raise ValueError("Stage 1 requires timestep_s == 0.1")
        return self

    def all_actors(self) -> list[Actor]:
        return [self.ego, *self.actors]


class ValidationIssue(StrictModel):
    code: str
    message: str
    path: str | None = None


class ValidateRequest(StrictModel):
    scenario: ScenarioSpec


class ValidateResponse(StrictModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class SimulateRequest(StrictModel):
    scenario: ScenarioSpec


class ActorFrameState(StrictModel):
    id: str
    x: float
    y: float
    vx: float
    vy: float
    heading_deg: float
    length: float
    width: float
    actor_type: str


class SimulationFrame(StrictModel):
    t: NonNegFloat
    actors: list[ActorFrameState]
    collisions: list[tuple[str, str]] = Field(default_factory=list)
    ego_speed: NonNegFloat
    min_ttc: float | None = None


class SimulationMetrics(StrictModel):
    duration_s: float
    timestep_s: float
    frame_count: int
    collision_count: int
    min_ttc: float | None
    max_acceleration: float
    max_jerk: float
    lane_boundary_violations: int
    initial_overlap: bool
    oracle_results: list[OracleResult]


class SimulateResponse(StrictModel):
    scenario_id: str
    valid: bool
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    frames: list[SimulationFrame] = Field(default_factory=list)
    metrics: SimulationMetrics | None = None
    trajectories: dict[str, list[tuple[float, float]]] = Field(default_factory=dict)


class PresetSummary(StrictModel):
    id: str
    name: str
    description: str
    default_testing_goal: str = ""
    kind: str = Field(
        default="scenario",
        description="scenario | impossible  -  demo classification for the UI",
    )


class HealthResponse(StrictModel):
    status: str
    service: str
    version: str
    deterministic: bool


class CompileRequest(StrictModel):
    """Compile a seed scene + natural-language testing goal via OpenAI (server-side)."""

    seed_scene: ScenarioSpec
    testing_goal: str = Field(..., min_length=1)
    run_simulation: bool = True


class CompileResponse(StrictModel):
    mode: str
    model: str | None = None
    ok: bool
    error_code: str | None = None
    error: str | None = None
    target_kind: str | None = None
    json_parse_ok: bool = False
    schema_valid: bool = False
    physical_valid: bool = False
    parsed: dict[str, Any] | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    simulation: SimulateResponse | None = None
    latency_s: float | None = None
    usage: dict[str, Any] | None = None
    # raw_text intentionally omitted from public API to keep payloads smaller;
    # available in offline eval artifacts only.
