"""DriveMutation — shared geometry and SI unit primitives.

All quantities use SI units: metres (m), seconds (s), m/s, m/s².
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


PositiveFloat = Annotated[float, Field(gt=0)]
NonNegFloat = Annotated[float, Field(ge=0)]


class StrictModel(BaseModel):
    """Base model: forbid extras, validate on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Position2D(StrictModel):
    """World-frame position in metres."""

    x: float = Field(..., description="Eastward position [m]")
    y: float = Field(..., description="Northward position [m]")


class Velocity2D(StrictModel):
    """World-frame velocity in m/s."""

    vx: float = Field(..., description="Eastward velocity [m/s]")
    vy: float = Field(..., description="Northward velocity [m/s]")

    @property
    def speed(self) -> float:
        return (self.vx**2 + self.vy**2) ** 0.5


class Dimensions2D(StrictModel):
    """Axis-aligned bounding box size in metres (length along heading, width perpendicular)."""

    length: PositiveFloat = Field(..., description="Longitudinal extent [m]")
    width: PositiveFloat = Field(..., description="Lateral extent [m]")


class ActorType(str, Enum):
    EGO = "ego"
    VEHICLE = "vehicle"
    CYCLIST = "cyclist"
    PEDESTRIAN = "pedestrian"


class BehaviorType(str, Enum):
    CONSTANT_VELOCITY = "constant_velocity"
    TRIGGERED_CROSSING = "triggered_crossing"
    TRIGGERED_CUT_IN = "triggered_cut_in"
    PARKED = "parked"
    STOPPED = "stopped"


class TriggerType(str, Enum):
    TIME = "time"
    EGO_DISTANCE = "ego_distance"
    EGO_ENTER_REGION = "ego_enter_region"


class MutationOp(str, Enum):
    SET_SPEED = "set_speed"
    SHIFT_POSITION = "shift_position"
    CHANGE_TRIGGER_TIME = "change_trigger_time"
    ADD_ACTOR = "add_actor"
    REMOVE_ACTOR = "remove_actor"
    CHANGE_BEHAVIOR = "change_behavior"


class OracleType(str, Enum):
    NO_COLLISION = "no_collision"
    MIN_TTC = "min_ttc"
    MAX_ACCELERATION = "max_acceleration"
    MAX_JERK = "max_jerk"
    LANE_KEEPING = "lane_keeping"
    NO_INITIAL_OVERLAP = "no_initial_overlap"


class Assumption(StrictModel):
    """Explicit modelling assumption recorded with a scenario."""

    id: str
    statement: str


class Unknown(StrictModel):
    """Explicit unknown / out-of-scope item for Stage 1."""

    id: str
    statement: str
