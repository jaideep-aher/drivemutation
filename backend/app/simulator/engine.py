"""Deterministic 2D scenario simulator — fixed 0.1 s timestep."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.app.schemas.common import BehaviorType, OracleType, TriggerType
from backend.app.schemas.oracles import OracleResult
from backend.app.schemas.scenario import (
    ActorFrameState,
    ScenarioSpec,
    SimulationFrame,
    SimulationMetrics,
    SimulateResponse,
)
from backend.app.simulator.collision import OBB, boxes_overlap, point_in_aabb
from backend.app.simulator.metrics import finite_diff, relative_ttc, speed
from backend.app.simulator.mutations import apply_mutations


DT = 0.1  # Stage-1 fixed timestep [s]


@dataclass
class RuntimeActor:
    id: str
    actor_type: str
    x: float
    y: float
    vx: float
    vy: float
    length: float
    width: float
    heading_deg: float
    lane_id: str | None
    behavior_type: BehaviorType
    trigger_id: str | None
    post_vx: float | None = None
    post_vy: float | None = None
    target_lane_id: str | None = None
    lateral_speed: float | None = None
    triggered: bool = False
    cut_in_complete: bool = False


@dataclass
class SimState:
    actors: dict[str, RuntimeActor]
    fired_triggers: set[str] = field(default_factory=set)
    collision_pairs: set[tuple[str, str]] = field(default_factory=set)
    lane_violations: int = 0
    ego_speeds: list[float] = field(default_factory=list)
    ego_accels: list[float] = field(default_factory=list)
    ttc_samples: list[float] = field(default_factory=list)


def simulate(scenario: ScenarioSpec) -> SimulateResponse:
    """Run a full deterministic simulation. Caller should validate first."""
    scenario = apply_mutations(scenario)
    dt = scenario.timestep_s
    assert abs(dt - DT) < 1e-12

    state = _init_state(scenario)
    frames: list[SimulationFrame] = []
    trajectories: dict[str, list[tuple[float, float]]] = {
        a.id: [] for a in state.actors.values()
    }

    initial_overlap = _any_overlap(state)
    n_steps = int(round(scenario.duration_s / dt))
    prev_ego_speed = speed(state.actors[scenario.ego.id].vx, state.actors[scenario.ego.id].vy)
    prev_ego_accel = 0.0
    max_accel = 0.0
    max_jerk = 0.0

    for step in range(n_steps + 1):
        t = round(step * dt, 10)
        _update_triggers(scenario, state, t)
        _apply_behaviors(scenario, state, dt)

        frame_collisions = _detect_collisions(state)
        for pair in frame_collisions:
            state.collision_pairs.add(pair)

        ego = state.actors[scenario.ego.id]
        ego_spd = speed(ego.vx, ego.vy)
        state.ego_speeds.append(ego_spd)

        if step > 0:
            accel = finite_diff(prev_ego_speed, ego_spd, dt)
            state.ego_accels.append(accel)
            max_accel = max(max_accel, abs(accel))
            jerk = finite_diff(prev_ego_accel, accel, dt)
            max_jerk = max(max_jerk, abs(jerk))
            prev_ego_accel = accel
        prev_ego_speed = ego_spd

        frame_ttc = _min_ttc_vs_ego(scenario.ego.id, state)
        if frame_ttc is not None:
            state.ttc_samples.append(frame_ttc)

        state.lane_violations += _count_lane_violations(scenario, state)

        actor_states = [
            ActorFrameState(
                id=a.id,
                x=round(a.x, 10),
                y=round(a.y, 10),
                vx=round(a.vx, 10),
                vy=round(a.vy, 10),
                heading_deg=round(a.heading_deg, 10),
                length=a.length,
                width=a.width,
                actor_type=a.actor_type,
            )
            for a in state.actors.values()
        ]
        frames.append(
            SimulationFrame(
                t=t,
                actors=actor_states,
                collisions=sorted(frame_collisions),
                ego_speed=round(ego_spd, 10),
                min_ttc=None if frame_ttc is None else round(frame_ttc, 10),
            )
        )
        for a in state.actors.values():
            trajectories[a.id].append((round(a.x, 10), round(a.y, 10)))

        if step < n_steps:
            _integrate(state, dt)

    global_min_ttc = min(state.ttc_samples) if state.ttc_samples else None
    oracle_results = _evaluate_oracles(
        scenario,
        collision_count=len(state.collision_pairs),
        min_ttc=global_min_ttc,
        max_accel=max_accel,
        max_jerk=max_jerk,
        lane_violations=state.lane_violations,
        initial_overlap=initial_overlap,
    )

    metrics = SimulationMetrics(
        duration_s=scenario.duration_s,
        timestep_s=dt,
        frame_count=len(frames),
        collision_count=len(state.collision_pairs),
        min_ttc=None if global_min_ttc is None else round(global_min_ttc, 10),
        max_acceleration=round(max_accel, 10),
        max_jerk=round(max_jerk, 10),
        lane_boundary_violations=state.lane_violations,
        initial_overlap=initial_overlap,
        oracle_results=oracle_results,
    )

    return SimulateResponse(
        scenario_id=scenario.id,
        valid=True,
        frames=frames,
        metrics=metrics,
        trajectories=trajectories,
    )


def _init_state(scenario: ScenarioSpec) -> SimState:
    actors: dict[str, RuntimeActor] = {}
    for a in scenario.all_actors():
        post_vx = post_vy = None
        if a.behavior.post_trigger_velocity is not None:
            post_vx = a.behavior.post_trigger_velocity.vx
            post_vy = a.behavior.post_trigger_velocity.vy
        vx, vy = a.velocity.vx, a.velocity.vy
        if a.behavior.type in {BehaviorType.PARKED, BehaviorType.STOPPED}:
            vx, vy = 0.0, 0.0
        actors[a.id] = RuntimeActor(
            id=a.id,
            actor_type=a.actor_type.value,
            x=a.position.x,
            y=a.position.y,
            vx=vx,
            vy=vy,
            length=a.dimensions.length,
            width=a.dimensions.width,
            heading_deg=a.heading_deg,
            lane_id=a.lane_id,
            behavior_type=a.behavior.type,
            trigger_id=a.behavior.trigger_id,
            post_vx=post_vx,
            post_vy=post_vy,
            target_lane_id=a.behavior.target_lane_id,
            lateral_speed=a.behavior.lateral_speed,
        )
    return SimState(actors=actors)


def _update_triggers(scenario: ScenarioSpec, state: SimState, t: float) -> None:
    ego = state.actors[scenario.ego.id]
    for trig in scenario.triggers:
        if trig.id in state.fired_triggers:
            continue
        fired = False
        if trig.type == TriggerType.TIME:
            assert trig.time_s is not None
            fired = t + 1e-12 >= trig.time_s
        elif trig.type == TriggerType.EGO_DISTANCE:
            assert trig.reference_point is not None and trig.distance_m is not None
            dist = math.hypot(
                ego.x - trig.reference_point.x, ego.y - trig.reference_point.y
            )
            fired = dist <= trig.distance_m
        elif trig.type == TriggerType.EGO_ENTER_REGION:
            assert trig.reference_point is not None and trig.region_half_extent_m is not None
            fired = point_in_aabb(
                ego.x,
                ego.y,
                trig.reference_point.x,
                trig.reference_point.y,
                trig.region_half_extent_m,
            )
        if fired:
            state.fired_triggers.add(trig.id)


def _apply_behaviors(scenario: ScenarioSpec, state: SimState, dt: float) -> None:
    lane_lookup = {lane.id: lane for lane in scenario.road.lanes}
    for actor in state.actors.values():
        if actor.behavior_type in {BehaviorType.PARKED, BehaviorType.STOPPED}:
            actor.vx = 0.0
            actor.vy = 0.0
            continue
        if actor.behavior_type == BehaviorType.CONSTANT_VELOCITY:
            continue
        if actor.behavior_type == BehaviorType.TRIGGERED_CROSSING:
            if actor.trigger_id and actor.trigger_id in state.fired_triggers:
                if not actor.triggered:
                    actor.triggered = True
                    actor.vx = actor.post_vx or 0.0
                    actor.vy = actor.post_vy or 0.0
                    actor.heading_deg = math.degrees(math.atan2(actor.vy, actor.vx)) if speed(actor.vx, actor.vy) > 1e-9 else actor.heading_deg
            else:
                actor.vx = 0.0
                actor.vy = 0.0
        elif actor.behavior_type == BehaviorType.TRIGGERED_CUT_IN:
            if actor.trigger_id and actor.trigger_id in state.fired_triggers and not actor.cut_in_complete:
                actor.triggered = True
                target = lane_lookup.get(actor.target_lane_id or "")
                if target is None:
                    actor.vx = actor.post_vx or actor.vx
                    actor.vy = actor.post_vy or 0.0
                else:
                    dy = target.center_y - actor.y
                    lat = actor.lateral_speed if actor.lateral_speed is not None else 2.0
                    if abs(dy) <= abs(lat) * dt + 1e-6:
                        actor.y = target.center_y
                        actor.lane_id = target.id
                        actor.vy = 0.0
                        actor.vx = actor.post_vx if actor.post_vx is not None else actor.vx
                        actor.cut_in_complete = True
                    else:
                        actor.vy = math.copysign(lat, dy)
                        if actor.post_vx is not None:
                            actor.vx = actor.post_vx
                actor.heading_deg = math.degrees(math.atan2(actor.vy, actor.vx)) if speed(actor.vx, actor.vy) > 1e-9 else actor.heading_deg


def _integrate(state: SimState, dt: float) -> None:
    for actor in state.actors.values():
        actor.x += actor.vx * dt
        actor.y += actor.vy * dt


def _obb(a: RuntimeActor) -> OBB:
    return OBB(
        x=a.x,
        y=a.y,
        length=a.length,
        width=a.width,
        heading_rad=math.radians(a.heading_deg),
    )


def _detect_collisions(state: SimState) -> list[tuple[str, str]]:
    ids = sorted(state.actors.keys())
    hits: list[tuple[str, str]] = []
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            if boxes_overlap(_obb(state.actors[id_a]), _obb(state.actors[id_b])):
                hits.append((id_a, id_b))
    return hits


def _any_overlap(state: SimState) -> bool:
    return len(_detect_collisions(state)) > 0


def _min_ttc_vs_ego(ego_id: str, state: SimState) -> float | None:
    ego = state.actors[ego_id]
    best: float | None = None
    for actor in state.actors.values():
        if actor.id == ego_id:
            continue
        radius = 0.5 * (math.hypot(ego.length, ego.width) + math.hypot(actor.length, actor.width))
        ttc = relative_ttc(
            ego.x, ego.y, ego.vx, ego.vy, actor.x, actor.y, actor.vx, actor.vy, radius
        )
        if ttc is None:
            continue
        best = ttc if best is None else min(best, ttc)
    return best


def _count_lane_violations(scenario: ScenarioSpec, state: SimState) -> int:
    """Count actors assigned to a lane whose centre is outside lane boundaries."""
    lane_lookup = {lane.id: lane for lane in scenario.road.lanes}
    count = 0
    for actor in state.actors.values():
        if not actor.lane_id or actor.lane_id not in lane_lookup:
            continue
        lane = lane_lookup[actor.lane_id]
        # Half-width of actor projected simply: check centre vs lane edges with margin
        if actor.y > lane.left_boundary or actor.y < lane.right_boundary:
            count += 1
    return count


def _evaluate_oracles(
    scenario: ScenarioSpec,
    *,
    collision_count: int,
    min_ttc: float | None,
    max_accel: float,
    max_jerk: float,
    lane_violations: int,
    initial_overlap: bool,
) -> list[OracleResult]:
    results: list[OracleResult] = []
    for oracle in scenario.oracles:
        if oracle.type == OracleType.NO_COLLISION:
            passed = collision_count == 0
            results.append(
                OracleResult(
                    id=oracle.id,
                    type=oracle.type,
                    passed=passed,
                    value=float(collision_count),
                    message="no collisions" if passed else f"{collision_count} collision pair(s)",
                )
            )
        elif oracle.type == OracleType.MIN_TTC:
            thr = oracle.threshold if oracle.threshold is not None else 0.0
            if min_ttc is None:
                passed = True
                value = None
                msg = "no closing encounters"
            else:
                passed = min_ttc >= thr
                value = min_ttc
                msg = f"min_ttc={min_ttc:.3f}s threshold={thr:.3f}s"
            results.append(
                OracleResult(
                    id=oracle.id,
                    type=oracle.type,
                    passed=passed,
                    value=value,
                    message=msg,
                )
            )
        elif oracle.type == OracleType.MAX_ACCELERATION:
            thr = oracle.threshold if oracle.threshold is not None else 0.0
            passed = max_accel <= thr
            results.append(
                OracleResult(
                    id=oracle.id,
                    type=oracle.type,
                    passed=passed,
                    value=max_accel,
                    message=f"max_|a|={max_accel:.3f} m/s² threshold={thr:.3f}",
                )
            )
        elif oracle.type == OracleType.MAX_JERK:
            thr = oracle.threshold if oracle.threshold is not None else 0.0
            passed = max_jerk <= thr
            results.append(
                OracleResult(
                    id=oracle.id,
                    type=oracle.type,
                    passed=passed,
                    value=max_jerk,
                    message=f"max_|j|={max_jerk:.3f} m/s³ threshold={thr:.3f}",
                )
            )
        elif oracle.type == OracleType.LANE_KEEPING:
            passed = lane_violations == 0
            results.append(
                OracleResult(
                    id=oracle.id,
                    type=oracle.type,
                    passed=passed,
                    value=float(lane_violations),
                    message="lane keeping ok" if passed else f"{lane_violations} violations",
                )
            )
        elif oracle.type == OracleType.NO_INITIAL_OVERLAP:
            passed = not initial_overlap
            results.append(
                OracleResult(
                    id=oracle.id,
                    type=oracle.type,
                    passed=passed,
                    value=1.0 if initial_overlap else 0.0,
                    message="no initial overlap" if passed else "actors overlap at t=0",
                )
            )
    return results
