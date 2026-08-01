"""Logical and concrete scenario schemas with required provenance."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    NHTSA_PRECRASH = "nhtsa_precrash"
    UNECE_R157 = "unece_r157"
    EURO_NCAP = "euro_ncap"
    NHTSA_SGO = "nhtsa_sgo"
    HAZOP = "hazop"


class ScenarioFamily(str, Enum):
    # The nine NHTSA crash groups (DOT HS 812 745, 2019).
    CONTROL_LOSS = "control_loss"
    ROAD_DEPARTURE = "road_departure"
    ANIMAL = "animal"
    PEDESTRIAN = "pedestrian"
    PEDALCYCLIST = "pedalcyclist"
    LANE_CHANGE = "lane_change"
    OPPOSITE_DIRECTION = "opposite_direction"
    REAR_END = "rear_end"
    CROSSING_PATHS = "crossing_paths"
    # Typology scenarios outside the nine groups, counted by NHTSA under
    # "remaining scenarios".
    BACKING = "backing"
    OBJECT = "object"
    EVASIVE_ACTION = "evasive_action"
    NON_COLLISION = "non_collision"
    VEHICLE_FAILURE = "vehicle_failure"
    # Regulation- and HAZOP-derived families that have no NHTSA equivalent.
    CUT_IN = "cut_in"
    CUT_OUT = "cut_out"
    DECELERATION = "deceleration"
    VRU_CROSSING = "vru_crossing"
    SENSOR_DEGRADATION = "sensor_degradation"
    UNKNOWN = "unknown"


class Weather(str, Enum):
    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class Lighting(str, Enum):
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"
    DAWN = "dawn"


class RoadGeometry(str, Enum):
    STRAIGHT = "straight"
    CURVE = "curve"
    INTERSECTION = "intersection"
    HIGHWAY = "highway"
    ROUNDABOUT = "roundabout"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    UNPREVENTABLE = "unpreventable"


class Provenance(BaseModel):
    source: SourceType
    citation: str = Field(..., description="Regulation clause, report ID, or guide word")
    parent_id: str | None = None
    seed: int = 0
    notes: str = ""


class ParamRange(BaseModel):
    min: float
    max: float
    unit: str = ""


class ActorSpec(BaseModel):
    actor_type: Literal["vehicle", "pedestrian", "cyclist", "animal", "static"]
    role: str = "other"
    length_m: float = 4.5
    width_m: float = 1.8
    height_m: float = 1.5
    behavior: str = "constant_velocity"


class LogicalScenario(BaseModel):
    id: str
    name: str
    family: ScenarioFamily
    description: str
    provenance: Provenance
    crash_frequency_weight: float = Field(
        1.0, description="Relative weight from NHTSA national crash stats"
    )
    nhtsa_scenario_number: int | None = Field(
        None, description="Position in the NHTSA pre-crash typology (1-37), if applicable"
    )
    annual_crashes: int | None = Field(
        None, description="Published annual crash count (DOT HS 810 767 Table 13, 2004 GES)"
    )
    crash_share_pct: float | None = Field(
        None, description="Published share of all light-vehicle crashes, percent"
    )
    simulable: bool = Field(
        True,
        description=(
            "False when the kinematic layer cannot faithfully represent the "
            "scenario, so it is catalogued but not expanded into concrete variants"
        ),
    )
    road_geometries: list[RoadGeometry]
    weathers: list[Weather]
    lightings: list[Lighting]
    ego_speed_kph: ParamRange
    actor_speed_kph: ParamRange
    distance_m: ParamRange
    ttc_s: ParamRange | None = None
    actors: list[ActorSpec]
    odd_params: dict[str, list[Any]] = Field(default_factory=dict)
    r157_params: dict[str, float] = Field(default_factory=dict)


class ActorState(BaseModel):
    id: str
    actor_type: str
    x: float
    y: float
    z: float = 0.0
    vx: float
    vy: float
    heading_deg: float
    length_m: float
    width_m: float
    height_m: float
    behavior: str = "constant_velocity"
    trigger_t: float | None = None
    post_vx: float | None = None
    post_vy: float | None = None
    lateral_speed: float | None = None
    target_y: float | None = None


class CriticalityMetrics(BaseModel):
    min_ttc_s: float | None = None
    min_distance_m: float | None = None
    min_clearance_m: float | None = Field(
        None,
        description=(
            "Closest bounding-box clearance, negative once the boxes overlap. "
            "Signed and continuous through contact, so a criticality search can "
            "bisect on the point where a collision begins"
        ),
    )
    pet_s: float | None = None
    required_decel_mps2: float | None = None
    collision: bool = False
    preventable: bool | None = None


class ConcreteScenario(BaseModel):
    id: str
    logical_id: str
    family: ScenarioFamily
    name: str
    provenance: Provenance
    weather: Weather
    lighting: Lighting
    road_geometry: RoadGeometry
    duration_s: float = 8.0
    timestep_s: float = 0.1
    ego: ActorState
    actors: list[ActorState]
    odd: dict[str, Any] = Field(default_factory=dict)
    crash_frequency_weight: float = 1.0
    metrics: CriticalityMetrics | None = None
    difficulty: Difficulty | None = None


class Box3D(BaseModel):
    instance_id: int
    category: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    heading_deg: float
    vx: float = 0.0
    vy: float = 0.0
    occlusion: float = 0.0  # 0=visible, 1=fully occluded
    num_lidar_hits: int = 0


class PointCloudFrame(BaseModel):
    t: float
    # Flat arrays for wire efficiency; frontend rebuilds
    xyz: list[float]  # N*3
    intensity: list[float]
    semantic: list[int]
    instance: list[int]
    boxes: list[Box3D]
    radar_xyz: list[float] = Field(default_factory=list)
    radar_doppler: list[float] = Field(default_factory=list)
    radar_rcs: list[float] = Field(default_factory=list)


class RenderRequest(BaseModel):
    scenario_id: str
    frame_idx: int | None = None  # None = all frames (or subsampled)
    degrade: bool = True
    max_frames: int = 20
    lidar_beams: int = 32
    lidar_azimuth: int = 256


class ScenarioSummary(BaseModel):
    id: str
    logical_id: str
    family: ScenarioFamily
    name: str
    weather: Weather
    lighting: Lighting
    road_geometry: RoadGeometry
    difficulty: Difficulty | None = None
    min_ttc_s: float | None = None
    collision: bool = False
    provenance_citation: str
    crash_frequency_weight: float = 1.0


class CoverageStats(BaseModel):
    total_concrete: int
    total_logical: int
    by_family: dict[str, int]
    by_weather: dict[str, int]
    by_lighting: dict[str, int]
    by_difficulty: dict[str, int]
    by_road: dict[str, int]
    gap_count: int = 0


class GapItem(BaseModel):
    incident_id: str
    narrative: str
    manufacturer: str = ""
    date: str = ""
    reason: str = "no matching catalog family"


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    concrete_count: int
    logical_count: int
