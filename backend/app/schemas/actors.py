"""Actor schemas  -  ego, vehicles, cyclists, pedestrians."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import (
    ActorType,
    Dimensions2D,
    Position2D,
    StrictModel,
    Velocity2D,
)
from .behavior import ActorBehavior


class ActorBase(StrictModel):
    """Shared fields for all scenario actors."""

    id: str = Field(..., min_length=1)
    actor_type: ActorType
    position: Position2D
    velocity: Velocity2D
    dimensions: Dimensions2D
    lane_id: str | None = Field(
        default=None, description="Lane id if assigned; None for off-road / crossing"
    )
    heading_deg: float = Field(
        default=0.0,
        description="Yaw angle in degrees; 0 = +x, 90 = +y",
    )
    behavior: ActorBehavior


class EgoVehicle(ActorBase):
    actor_type: ActorType = ActorType.EGO

    @model_validator(mode="after")
    def _force_ego(self) -> EgoVehicle:
        if self.actor_type != ActorType.EGO:
            raise ValueError("EgoVehicle.actor_type must be 'ego'")
        return self


class VehicleActor(ActorBase):
    actor_type: ActorType = ActorType.VEHICLE

    @model_validator(mode="after")
    def _force_vehicle(self) -> VehicleActor:
        if self.actor_type != ActorType.VEHICLE:
            raise ValueError("VehicleActor.actor_type must be 'vehicle'")
        return self


class CyclistActor(ActorBase):
    actor_type: ActorType = ActorType.CYCLIST

    @model_validator(mode="after")
    def _force_cyclist(self) -> CyclistActor:
        if self.actor_type != ActorType.CYCLIST:
            raise ValueError("CyclistActor.actor_type must be 'cyclist'")
        return self


class PedestrianActor(ActorBase):
    actor_type: ActorType = ActorType.PEDESTRIAN

    @model_validator(mode="after")
    def _force_pedestrian(self) -> PedestrianActor:
        if self.actor_type != ActorType.PEDESTRIAN:
            raise ValueError("PedestrianActor.actor_type must be 'pedestrian'")
        return self


Actor = EgoVehicle | VehicleActor | CyclistActor | PedestrianActor
