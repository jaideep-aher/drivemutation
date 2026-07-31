"""Mutation application  -  deterministic, ordered."""

from __future__ import annotations

import math

from backend.app.schemas.common import MutationOp, Velocity2D
from backend.app.schemas.mutations import MutationSpec
from backend.app.schemas.scenario import ScenarioSpec


def apply_mutations(scenario: ScenarioSpec) -> ScenarioSpec:
    """Return a deep-copied scenario with mutation ops applied in order."""
    out = scenario.model_copy(deep=True)
    if out.mutation is None:
        return out
    return _apply_ops(out, out.mutation)


def _apply_ops(scenario: ScenarioSpec, spec: MutationSpec) -> ScenarioSpec:
    for op in spec.operations:
        if op.op == MutationOp.SET_SPEED:
            _set_speed(scenario, op.actor_id, op.speed_mps)  # type: ignore[arg-type]
        elif op.op == MutationOp.SHIFT_POSITION:
            actor = _find_actor(scenario, op.actor_id)  # type: ignore[arg-type]
            actor.position.x += op.position_delta.x  # type: ignore[union-attr]
            actor.position.y += op.position_delta.y  # type: ignore[union-attr]
        elif op.op == MutationOp.CHANGE_TRIGGER_TIME:
            for t in scenario.triggers:
                if t.id == op.trigger_id:
                    t.time_s = op.new_time_s
        elif op.op == MutationOp.ADD_ACTOR:
            assert op.actor is not None
            # Ego cannot be added via mutation in Stage 1
            from backend.app.schemas.actors import EgoVehicle

            if isinstance(op.actor, EgoVehicle) or op.actor.actor_type.value == "ego":
                raise ValueError("Cannot add ego via mutation")
            scenario.actors.append(op.actor)  # type: ignore[arg-type]
        elif op.op == MutationOp.REMOVE_ACTOR:
            if op.actor_id == scenario.ego.id:
                raise ValueError("Cannot remove ego")
            scenario.actors = [a for a in scenario.actors if a.id != op.actor_id]
        elif op.op == MutationOp.CHANGE_BEHAVIOR:
            actor = _find_actor(scenario, op.actor_id)  # type: ignore[arg-type]
            actor.behavior = op.behavior  # type: ignore[assignment]
    return scenario


def _find_actor(scenario: ScenarioSpec, actor_id: str):
    if scenario.ego.id == actor_id:
        return scenario.ego
    for a in scenario.actors:
        if a.id == actor_id:
            return a
    raise ValueError(f"Actor not found: {actor_id}")


def _set_speed(scenario: ScenarioSpec, actor_id: str, speed_mps: float) -> None:
    actor = _find_actor(scenario, actor_id)
    mag = math.hypot(actor.velocity.vx, actor.velocity.vy)
    if mag < 1e-9:
        # Preserve heading from heading_deg
        rad = math.radians(actor.heading_deg)
        actor.velocity = Velocity2D(vx=speed_mps * math.cos(rad), vy=speed_mps * math.sin(rad))
    else:
        scale = speed_mps / mag
        actor.velocity = Velocity2D(vx=actor.velocity.vx * scale, vy=actor.velocity.vy * scale)
