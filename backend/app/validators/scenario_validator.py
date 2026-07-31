"""Deterministic scenario validators."""

from __future__ import annotations

import math

from backend.app.schemas.common import BehaviorType, TriggerType
from backend.app.schemas.scenario import ScenarioSpec, ValidationIssue
from backend.app.simulator.collision import OBB, boxes_overlap
from backend.app.simulator.mutations import apply_mutations

# Stage-1 physical bounds (SI)
MAX_SPEED_MPS = {
    "ego": 40.0,
    "vehicle": 40.0,
    "cyclist": 15.0,
    "pedestrian": 4.0,
}
MAX_ACCEL_DECLARED = 8.0  # m/s²  -  reserved for future accel profiles
MIN_ACTOR_SIZE = 0.2  # m
MAX_ACTOR_LENGTH = 12.0
MAX_ACTOR_WIDTH = 3.0


def validate_scenario(scenario: ScenarioSpec) -> list[ValidationIssue]:
    """Return validation issues; empty list means accept."""
    issues: list[ValidationIssue] = []
    try:
        scenario = apply_mutations(scenario)
    except Exception as exc:  # noqa: BLE001  -  surface mutation errors as validation
        issues.append(
            ValidationIssue(code="mutation_error", message=str(exc), path="mutation")
        )
        return issues

    issues.extend(_check_timestep(scenario))
    issues.extend(_check_ids(scenario))
    issues.extend(_check_bounds(scenario))
    issues.extend(_check_placement(scenario))
    issues.extend(_check_initial_collisions(scenario))
    issues.extend(_check_triggers(scenario))
    issues.extend(_check_oracles(scenario))
    issues.extend(_check_contradictions(scenario))
    return issues


def _check_timestep(scenario: ScenarioSpec) -> list[ValidationIssue]:
    if abs(scenario.timestep_s - 0.1) > 1e-12:
        return [
            ValidationIssue(
                code="invalid_timestep",
                message="timestep_s must be 0.1",
                path="timestep_s",
            )
        ]
    return []


def _check_ids(scenario: ScenarioSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ids = [a.id for a in scenario.all_actors()]
    if len(ids) != len(set(ids)):
        issues.append(
            ValidationIssue(code="duplicate_actor_id", message="Actor ids must be unique")
        )
    lane_ids = {lane.id for lane in scenario.road.lanes}
    for actor in scenario.all_actors():
        if actor.lane_id and actor.lane_id not in lane_ids:
            issues.append(
                ValidationIssue(
                    code="unknown_lane",
                    message=f"Actor {actor.id} references unknown lane_id={actor.lane_id}",
                    path=f"actors.{actor.id}.lane_id",
                )
            )
    trig_ids = [t.id for t in scenario.triggers]
    if len(trig_ids) != len(set(trig_ids)):
        issues.append(
            ValidationIssue(code="duplicate_trigger_id", message="Trigger ids must be unique")
        )
    return issues


def _check_bounds(scenario: ScenarioSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for actor in scenario.all_actors():
        spd = math.hypot(actor.velocity.vx, actor.velocity.vy)
        limit = MAX_SPEED_MPS.get(actor.actor_type.value, 40.0)
        if spd > limit + 1e-9:
            issues.append(
                ValidationIssue(
                    code="speed_out_of_bounds",
                    message=f"{actor.id} speed {spd:.2f} m/s exceeds {limit} m/s",
                    path=f"actors.{actor.id}.velocity",
                )
            )
        if actor.dimensions.length > MAX_ACTOR_LENGTH or actor.dimensions.width > MAX_ACTOR_WIDTH:
            issues.append(
                ValidationIssue(
                    code="dimensions_out_of_bounds",
                    message=f"{actor.id} dimensions exceed Stage-1 limits",
                    path=f"actors.{actor.id}.dimensions",
                )
            )
        if actor.dimensions.length < MIN_ACTOR_SIZE or actor.dimensions.width < MIN_ACTOR_SIZE:
            issues.append(
                ValidationIssue(
                    code="dimensions_too_small",
                    message=f"{actor.id} dimensions below minimum",
                    path=f"actors.{actor.id}.dimensions",
                )
            )
        if actor.behavior.type in {BehaviorType.PARKED, BehaviorType.STOPPED} and spd > 1e-6:
            issues.append(
                ValidationIssue(
                    code="parked_nonzero_speed",
                    message=f"{actor.id} is parked/stopped but has nonzero velocity",
                    path=f"actors.{actor.id}.velocity",
                )
            )
    return issues


def _check_placement(scenario: ScenarioSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    road = scenario.road
    for actor in scenario.all_actors():
        if actor.position.x < -5.0 or actor.position.x > road.length + 5.0:
            issues.append(
                ValidationIssue(
                    code="actor_outside_road_extent",
                    message=f"{actor.id} x={actor.position.x} outside road extent",
                    path=f"actors.{actor.id}.position",
                )
            )
        if actor.lane_id:
            lane = next(l for l in road.lanes if l.id == actor.lane_id)
            # Placement must start roughly in lane (centre within boundaries)
            if actor.position.y > lane.left_boundary + 0.5 or actor.position.y < lane.right_boundary - 0.5:
                issues.append(
                    ValidationIssue(
                        code="actor_not_in_lane",
                        message=f"{actor.id} y not within lane {lane.id} boundaries",
                        path=f"actors.{actor.id}.position",
                    )
                )
    return issues


def _check_initial_collisions(scenario: ScenarioSpec) -> list[ValidationIssue]:
    actors = list(scenario.all_actors())
    issues: list[ValidationIssue] = []
    for i, a in enumerate(actors):
        oa = OBB(
            a.position.x,
            a.position.y,
            a.dimensions.length,
            a.dimensions.width,
            math.radians(a.heading_deg),
        )
        for b in actors[i + 1 :]:
            ob = OBB(
                b.position.x,
                b.position.y,
                b.dimensions.length,
                b.dimensions.width,
                math.radians(b.heading_deg),
            )
            if boxes_overlap(oa, ob):
                issues.append(
                    ValidationIssue(
                        code="initial_collision",
                        message=f"Actors {a.id} and {b.id} overlap at t=0",
                    )
                )
    return issues


def _check_triggers(scenario: ScenarioSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    trig_map = {t.id: t for t in scenario.triggers}
    for actor in scenario.all_actors():
        if actor.behavior.type in {
            BehaviorType.TRIGGERED_CROSSING,
            BehaviorType.TRIGGERED_CUT_IN,
        }:
            tid = actor.behavior.trigger_id
            if not tid or tid not in trig_map:
                issues.append(
                    ValidationIssue(
                        code="missing_trigger",
                        message=f"{actor.id} references missing trigger {tid}",
                        path=f"actors.{actor.id}.behavior.trigger_id",
                    )
                )
                continue
            trig = trig_map[tid]
            if not _trigger_reachable(scenario, trig):
                issues.append(
                    ValidationIssue(
                        code="unreachable_trigger",
                        message=f"Trigger {tid} appears unreachable within duration",
                        path=f"triggers.{tid}",
                    )
                )
    return issues


def _trigger_reachable(scenario: ScenarioSpec, trig) -> bool:
    if trig.type == TriggerType.TIME:
        return trig.time_s is not None and trig.time_s <= scenario.duration_s + 1e-9
    if trig.type == TriggerType.EGO_DISTANCE:
        ego = scenario.ego
        # Conservative: if ego has motion toward reference or starts close enough
        assert trig.reference_point is not None and trig.distance_m is not None
        dx = trig.reference_point.x - ego.position.x
        dy = trig.reference_point.y - ego.position.y
        dist0 = math.hypot(dx, dy)
        if dist0 <= trig.distance_m:
            return True
        spd = math.hypot(ego.velocity.vx, ego.velocity.vy)
        if spd < 1e-9:
            return False
        # Max distance ego can travel
        return dist0 - spd * scenario.duration_s <= trig.distance_m + 1.0
    if trig.type == TriggerType.EGO_ENTER_REGION:
        ego = scenario.ego
        assert trig.reference_point is not None and trig.region_half_extent_m is not None
        # Approximate reachability along constant velocity ray
        cx, cy = trig.reference_point.x, trig.reference_point.y
        half = trig.region_half_extent_m
        # Sample coarse future positions
        dt = 0.1
        steps = int(scenario.duration_s / dt) + 1
        x, y = ego.position.x, ego.position.y
        for _ in range(steps):
            if abs(x - cx) <= half and abs(y - cy) <= half:
                return True
            x += ego.velocity.vx * dt
            y += ego.velocity.vy * dt
        return False
    return True


def _check_oracles(scenario: ScenarioSpec) -> list[ValidationIssue]:
    meaningful = {
        "no_collision",
        "min_ttc",
        "max_acceleration",
        "max_jerk",
        "lane_keeping",
        "no_initial_overlap",
    }
    if not scenario.oracles:
        return [
            ValidationIssue(
                code="no_oracle",
                message="At least one meaningful safety oracle is required",
                path="oracles",
            )
        ]
    if not any(o.type.value in meaningful for o in scenario.oracles):
        return [
            ValidationIssue(
                code="no_meaningful_oracle",
                message="Oracles present but none are recognized as meaningful",
                path="oracles",
            )
        ]
    return []


def _check_contradictions(scenario: ScenarioSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    # Ego parked + nonzero duration with distance trigger expecting motion
    ego = scenario.ego
    if ego.behavior.type in {BehaviorType.PARKED, BehaviorType.STOPPED}:
        for trig in scenario.triggers:
            if trig.type in {TriggerType.EGO_DISTANCE, TriggerType.EGO_ENTER_REGION}:
                # Only contradictory if ego starts outside the condition
                if trig.type == TriggerType.EGO_DISTANCE:
                    assert trig.reference_point is not None and trig.distance_m is not None
                    dist = math.hypot(
                        ego.position.x - trig.reference_point.x,
                        ego.position.y - trig.reference_point.y,
                    )
                    if dist > trig.distance_m:
                        issues.append(
                            ValidationIssue(
                                code="contradictory_scenario",
                                message="Parked ego cannot reach EGO_DISTANCE trigger",
                                path="ego.behavior",
                            )
                        )
                if trig.type == TriggerType.EGO_ENTER_REGION:
                    assert trig.reference_point is not None and trig.region_half_extent_m is not None
                    if not (
                        abs(ego.position.x - trig.reference_point.x) <= trig.region_half_extent_m
                        and abs(ego.position.y - trig.reference_point.y)
                        <= trig.region_half_extent_m
                    ):
                        issues.append(
                            ValidationIssue(
                                code="contradictory_scenario",
                                message="Parked ego cannot enter EGO_ENTER_REGION trigger",
                                path="ego.behavior",
                            )
                        )
    # Opposite travel claimed on same lane centre with overlapping extents is ok;
    # contradiction: cut-in target lane missing already covered.
    # Wrong-way: direction vs velocity sign mismatch on assigned lane
    lane_map = {l.id: l for l in scenario.road.lanes}
    for actor in scenario.all_actors():
        if actor.lane_id and actor.lane_id in lane_map:
            lane = lane_map[actor.lane_id]
            # If mostly longitudinal motion, check sign vs lane direction
            if abs(actor.velocity.vx) > abs(actor.velocity.vy) + 1e-6:
                if actor.velocity.vx * lane.direction < -1e-6:
                    # Allowed for wrong-way scenarios  -  not a contradiction by itself.
                    pass
    return issues
