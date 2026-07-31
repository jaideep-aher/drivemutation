"""Mutation operation schemas (Stage 1: structured ops, applied before sim)."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import MutationOp, Position2D, StrictModel, Velocity2D
from .behavior import ActorBehavior
from .actors import Actor


class MutationOperation(StrictModel):
    """A single deterministic mutation applied to a base scenario."""

    op: MutationOp
    actor_id: str | None = None
    speed_mps: float | None = Field(default=None, description="New speed magnitude [m/s]")
    position_delta: Position2D | None = None
    trigger_id: str | None = None
    new_time_s: float | None = Field(default=None, description="New trigger time [s]")
    actor: Actor | None = None
    behavior: ActorBehavior | None = None

    @model_validator(mode="after")
    def _check_op(self) -> MutationOperation:
        if self.op == MutationOp.SET_SPEED:
            if not self.actor_id or self.speed_mps is None:
                raise ValueError("set_speed requires actor_id and speed_mps")
        elif self.op == MutationOp.SHIFT_POSITION:
            if not self.actor_id or self.position_delta is None:
                raise ValueError("shift_position requires actor_id and position_delta")
        elif self.op == MutationOp.CHANGE_TRIGGER_TIME:
            if not self.trigger_id or self.new_time_s is None:
                raise ValueError("change_trigger_time requires trigger_id and new_time_s")
        elif self.op == MutationOp.ADD_ACTOR:
            if self.actor is None:
                raise ValueError("add_actor requires actor")
        elif self.op == MutationOp.REMOVE_ACTOR:
            if not self.actor_id:
                raise ValueError("remove_actor requires actor_id")
        elif self.op == MutationOp.CHANGE_BEHAVIOR:
            if not self.actor_id or self.behavior is None:
                raise ValueError("change_behavior requires actor_id and behavior")
        return self


class MutationSpec(StrictModel):
    """Ordered list of mutations applied to a scenario before simulation."""

    id: str
    description: str = ""
    operations: list[MutationOperation] = Field(default_factory=list)
