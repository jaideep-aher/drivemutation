"""Trigger schemas for delayed actor behaviors."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import NonNegFloat, Position2D, StrictModel, TriggerType


class Trigger(StrictModel):
    """Condition that fires exactly once and may unlock triggered behaviors."""

    id: str
    type: TriggerType
    time_s: NonNegFloat | None = Field(
        default=None, description="Absolute simulation time [s] for TIME triggers"
    )
    distance_m: NonNegFloat | None = Field(
        default=None,
        description="Ego distance to reference point [m] for EGO_DISTANCE",
    )
    reference_point: Position2D | None = Field(
        default=None, description="Reference point [m] for distance / region triggers"
    )
    region_half_extent_m: NonNegFloat | None = Field(
        default=None,
        description="Axis-aligned half-extent of square region [m] for EGO_ENTER_REGION",
    )

    @model_validator(mode="after")
    def _check_fields(self) -> Trigger:
        if self.type == TriggerType.TIME:
            if self.time_s is None:
                raise ValueError("TIME trigger requires time_s")
        elif self.type == TriggerType.EGO_DISTANCE:
            if self.distance_m is None or self.reference_point is None:
                raise ValueError("EGO_DISTANCE requires distance_m and reference_point")
        elif self.type == TriggerType.EGO_ENTER_REGION:
            if self.reference_point is None or self.region_half_extent_m is None:
                raise ValueError(
                    "EGO_ENTER_REGION requires reference_point and region_half_extent_m"
                )
        return self
