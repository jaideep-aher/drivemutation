"""Deterministic canonical mutation / rejection target builders."""

from __future__ import annotations

import json

from backend.app.dataset.schemas import (
    ActorKind,
    FAMILY_TO_HAZARD,
    MutationTarget,
    RejectionReason,
    RejectionTarget,
    RoadLayoutKind,
    ScenarioFamily,
    TriggerKind,
)
from backend.app.schemas.actors import CyclistActor, PedestrianActor, VehicleActor
from backend.app.schemas.behavior import ActorBehavior
from backend.app.schemas.common import (
    BehaviorType,
    Dimensions2D,
    MutationOp,
    Position2D,
    Velocity2D,
)
from backend.app.schemas.mutations import MutationOperation, MutationSpec
from backend.app.schemas.scenario import ScenarioSpec


def _ego_y(road_kind: RoadLayoutKind) -> float:
    return -1.75 if road_kind == RoadLayoutKind.FOUR_WAY else 0.0


def _ego_lane(road_kind: RoadLayoutKind) -> str:
    return "lane_eb" if road_kind == RoadLayoutKind.FOUR_WAY else "lane_ego"


def _adj_lane(road_kind: RoadLayoutKind) -> str:
    return "lane_adj"


def _adj_y(road_kind: RoadLayoutKind) -> float:
    return -5.25 if road_kind == RoadLayoutKind.FOUR_WAY else 3.5


def _retune_time_trigger(seed: ScenarioSpec, time_s: float) -> list[MutationOperation]:
    ops: list[MutationOperation] = []
    for t in seed.triggers:
        if t.id == "t_main" and t.type.value == "time":
            ops.append(
                MutationOperation(
                    op=MutationOp.CHANGE_TRIGGER_TIME,
                    trigger_id="t_main",
                    new_time_s=time_s,
                )
            )
    return ops


def build_accepted_target(
    *,
    example_id: str,
    family: ScenarioFamily,
    road_kind: RoadLayoutKind,
    actor_kind: ActorKind,
    trigger_kind: TriggerKind,
    variant: int,
    seed: ScenarioSpec,
) -> MutationTarget:
    del actor_kind
    hazard = FAMILY_TO_HAZARD[family]
    ops: list[MutationOperation] = []
    ego_y = _ego_y(road_kind)
    ego_lane = _ego_lane(road_kind)
    adj = _adj_lane(road_kind)
    adj_y = _adj_y(road_kind)
    x_hazard = 38.0 + (variant % 3)

    if family == ScenarioFamily.OCCLUDED_PEDESTRIAN:
        ops.extend(_retune_time_trigger(seed, 1.5))
        if trigger_kind == TriggerKind.NONE:
            ped = PedestrianActor(
                id="haz_ped",
                actor_type="pedestrian",
                position=Position2D(x=x_hazard, y=-6.0),
                velocity=Velocity2D(vx=0.0, vy=1.4),
                dimensions=Dimensions2D(length=0.6, width=0.6),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            )
        else:
            ped = PedestrianActor(
                id="haz_ped",
                actor_type="pedestrian",
                position=Position2D(x=x_hazard, y=-6.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=0.6, width=0.6),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CROSSING,
                    trigger_id="t_main",
                    post_trigger_velocity=Velocity2D(vx=0.0, vy=1.5),
                ),
            )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=ped))

    elif family == ScenarioFamily.OCCLUDED_CYCLIST:
        ops.extend(_retune_time_trigger(seed, 1.8))
        if trigger_kind == TriggerKind.NONE:
            cyc = CyclistActor(
                id="haz_cyclist",
                actor_type="cyclist",
                position=Position2D(x=x_hazard, y=-7.0),
                velocity=Velocity2D(vx=0.0, vy=3.5),
                dimensions=Dimensions2D(length=1.8, width=0.7),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            )
        else:
            cyc = CyclistActor(
                id="haz_cyclist",
                actor_type="cyclist",
                position=Position2D(x=x_hazard, y=-7.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=1.8, width=0.7),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CROSSING,
                    trigger_id="t_main",
                    post_trigger_velocity=Velocity2D(vx=0.0, vy=4.0),
                ),
            )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=cyc))

    elif family in {ScenarioFamily.AGGRESSIVE_CUT_IN, ScenarioFamily.MERGE}:
        # Composition excludes NONE for these families.
        ops.extend(_retune_time_trigger(seed, 0.8 if family == ScenarioFamily.AGGRESSIVE_CUT_IN else 1.2))
        lat = 3.0 if family == ScenarioFamily.AGGRESSIVE_CUT_IN else 2.2
        cutter = VehicleActor(
            id="haz_cutter",
            actor_type="vehicle",
            position=Position2D(x=18.0 + (variant % 3), y=adj_y),
            velocity=Velocity2D(vx=14.0, vy=0.0),
            dimensions=Dimensions2D(length=4.4, width=1.8),
            lane_id=adj,
            heading_deg=0.0,
            behavior=ActorBehavior(
                type=BehaviorType.TRIGGERED_CUT_IN,
                trigger_id="t_main",
                post_trigger_velocity=Velocity2D(vx=13.0, vy=0.0),
                target_lane_id=ego_lane,
                lateral_speed=lat,
            ),
        )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=cutter))

    elif family == ScenarioFamily.UNPROTECTED_LEFT:
        ops.extend(_retune_time_trigger(seed, 1.0))
        if any(a.id == "oncoming_seed" for a in seed.actors):
            ops.append(
                MutationOperation(
                    op=MutationOp.SET_SPEED,
                    actor_id="oncoming_seed",
                    speed_mps=11.0 + (variant % 2),
                )
            )
            ops.append(
                MutationOperation(
                    op=MutationOp.SHIFT_POSITION,
                    actor_id="oncoming_seed",
                    position_delta=Position2D(x=-10.0, y=0.0),
                )
            )
        if trigger_kind == TriggerKind.NONE:
            cross = VehicleActor(
                id="haz_cross",
                actor_type="vehicle",
                position=Position2D(x=40.0, y=-16.0),
                velocity=Velocity2D(vx=0.0, vy=8.0),
                dimensions=Dimensions2D(length=4.5, width=1.8),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            )
        else:
            cross = VehicleActor(
                id="haz_cross",
                actor_type="vehicle",
                position=Position2D(x=40.0, y=-16.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=4.5, width=1.8),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CROSSING,
                    trigger_id="t_main",
                    post_trigger_velocity=Velocity2D(vx=0.0, vy=9.0),
                ),
            )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=cross))

    elif family == ScenarioFamily.CONSTRUCTION_ZONE:
        blocker = VehicleActor(
            id="haz_construction",
            actor_type="vehicle",
            position=Position2D(x=45.0, y=ego_y),
            velocity=Velocity2D(vx=0.0, vy=0.0),
            dimensions=Dimensions2D(length=6.0, width=2.2),
            lane_id=ego_lane,
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.PARKED),
        )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=blocker))
        if trigger_kind != TriggerKind.NONE:
            ops.extend(_retune_time_trigger(seed, 1.4))
            merge = VehicleActor(
                id="haz_merge",
                actor_type="vehicle",
                position=Position2D(x=20.0, y=adj_y),
                velocity=Velocity2D(vx=11.0, vy=0.0),
                dimensions=Dimensions2D(length=4.4, width=1.8),
                lane_id=adj,
                heading_deg=0.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CUT_IN,
                    trigger_id="t_main",
                    post_trigger_velocity=Velocity2D(vx=10.0, vy=0.0),
                    target_lane_id=ego_lane,
                    lateral_speed=2.5,
                ),
            )
            ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=merge))

    elif family == ScenarioFamily.EMERGENCY_VEHICLE:
        if trigger_kind == TriggerKind.NONE:
            ev = VehicleActor(
                id="haz_emergency",
                actor_type="vehicle",
                position=Position2D(x=58.0, y=ego_y),
                velocity=Velocity2D(vx=-16.0, vy=0.0),
                dimensions=Dimensions2D(length=5.2, width=2.1),
                lane_id=ego_lane,
                heading_deg=180.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            )
        else:
            ops.extend(_retune_time_trigger(seed, 1.0))
            ev = VehicleActor(
                id="haz_emergency",
                actor_type="vehicle",
                position=Position2D(x=14.0, y=adj_y),
                velocity=Velocity2D(vx=17.0, vy=0.0),
                dimensions=Dimensions2D(length=5.2, width=2.1),
                lane_id=adj,
                heading_deg=0.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CUT_IN,
                    trigger_id="t_main",
                    post_trigger_velocity=Velocity2D(vx=16.0, vy=0.0),
                    target_lane_id=ego_lane,
                    lateral_speed=2.8,
                ),
            )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=ev))

    elif family == ScenarioFamily.WRONG_WAY_VEHICLE:
        ww = VehicleActor(
            id="haz_wrong_way",
            actor_type="vehicle",
            position=Position2D(x=58.0 - (variant % 3), y=ego_y),
            velocity=Velocity2D(vx=-14.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id=ego_lane,
            heading_deg=180.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        )
        ops.append(MutationOperation(op=MutationOp.ADD_ACTOR, actor=ww))

    mut = MutationSpec(
        id=f"mut_{example_id}",
        description=f"Canonical mutation for {family.value}",
        operations=ops,
    )
    return MutationTarget(
        status="accepted",
        mutation=mut,
        activated_hazard=hazard,
        scenario_family=family,
    )


def build_rejection_target(*, variant: int, actor_label: str) -> RejectionTarget:
    catalog = [
        RejectionTarget(
            reasons=[
                RejectionReason(
                    code="physically_impossible",
                    message="Requested instantaneous teleportation / infinite acceleration is outside Stage-1 physics.",
                ),
                RejectionReason(
                    code="out_of_scope",
                    message="Non-continuous spatial jumps are not representable by MutationOp set.",
                ),
            ],
            notes=f"impossible_teleport:{actor_label}:{variant}",
        ),
        RejectionTarget(
            reasons=[
                RejectionReason(
                    code="contradictory_request",
                    message="Cannot remove ego while requiring ego-centric safety oracles.",
                )
            ],
            notes=f"remove_ego:{variant}",
        ),
        RejectionTarget(
            reasons=[
                RejectionReason(
                    code="speed_out_of_bounds",
                    message="Requested pedestrian speed 200 m/s exceeds Stage-1 pedestrian bound (4 m/s).",
                )
            ],
            notes=f"ped_overspeed:{variant}",
        ),
        RejectionTarget(
            reasons=[
                RejectionReason(
                    code="out_of_scope",
                    message="Flight / elevation outside planar 2D world model.",
                )
            ],
            notes=f"flight:{variant}",
        ),
        RejectionTarget(
            reasons=[
                RejectionReason(
                    code="out_of_scope",
                    message="Changing gravity / leaving the 2D plane is unsupported.",
                )
            ],
            notes=f"gravity:{variant}",
        ),
        RejectionTarget(
            reasons=[
                RejectionReason(
                    code="contradictory_scenario",
                    message="Parked ego cannot satisfy a distant ego-distance trigger.",
                )
            ],
            notes=f"parked_ego_trigger:{variant}",
        ),
    ]
    return catalog[variant % len(catalog)]


def target_to_canonical_json(target: MutationTarget | RejectionTarget) -> str:
    return json.dumps(target.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
