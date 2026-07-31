"""Actor behavior schemas."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import BehaviorType, StrictModel, Velocity2D


class ActorBehavior(StrictModel):
    """Deterministic motion policy for an actor.

    CONSTANT_VELOCITY / PARKED / STOPPED: no trigger required.
    TRIGGERED_CROSSING / TRIGGERED_CUT_IN: require trigger_id and post_trigger_velocity.
    """

    type: BehaviorType
    trigger_id: str | None = None
    post_trigger_velocity: Velocity2D | None = Field(
        default=None,
        description="Velocity applied after trigger fires [m/s]",
    )
    target_lane_id: str | None = Field(
        default=None,
        description="For cut-in: destination lane id",
    )
    lateral_speed: float | None = Field(
        default=None,
        description="For cut-in: lateral approach speed magnitude [m/s]",
    )

    @model_validator(mode="after")
    def _check_triggered(self) -> ActorBehavior:
        triggered = {BehaviorType.TRIGGERED_CROSSING, BehaviorType.TRIGGERED_CUT_IN}
        if self.type in triggered:
            if not self.trigger_id:
                raise ValueError(f"{self.type.value} requires trigger_id")
            if self.post_trigger_velocity is None:
                raise ValueError(f"{self.type.value} requires post_trigger_velocity")
        if self.type == BehaviorType.TRIGGERED_CUT_IN:
            if not self.target_lane_id:
                raise ValueError("triggered_cut_in requires target_lane_id")
        if self.type in {BehaviorType.PARKED, BehaviorType.STOPPED}:
            # parked/stopped imply zero motion after init; validator enforces velocity ~0
            pass
        return self
