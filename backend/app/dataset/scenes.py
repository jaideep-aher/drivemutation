"""Deterministic seed-scene builders parameterized by composition axes."""

from __future__ import annotations

from backend.app.dataset.schemas import (
    ActorKind,
    RoadLayoutKind,
    ScenarioFamily,
    TriggerKind,
)
from backend.app.presets.scenarios import DEFAULT_ASSUMPTIONS, DEFAULT_UNKNOWNS
from backend.app.schemas.actors import EgoVehicle, VehicleActor
from backend.app.schemas.behavior import ActorBehavior
from backend.app.schemas.common import (
    BehaviorType,
    Dimensions2D,
    OracleType,
    Position2D,
    TriggerType,
    Velocity2D,
)
from backend.app.schemas.oracles import SafetyOracle
from backend.app.schemas.road import Lane, RoadKind, RoadLayout
from backend.app.schemas.scenario import ScenarioSpec
from backend.app.schemas.triggers import Trigger


def build_road(kind: RoadLayoutKind, length: float = 80.0) -> RoadLayout:
    if kind == RoadLayoutKind.STRAIGHT_DUAL:
        return RoadLayout(
            kind=RoadKind.STRAIGHT,
            length=length,
            lanes=[
                Lane(id="lane_ego", center_y=0.0, width=3.5, direction=1),
                Lane(id="lane_adj", center_y=3.5, width=3.5, direction=1),
            ],
        )
    if kind == RoadLayoutKind.STRAIGHT_TRIPLE:
        return RoadLayout(
            kind=RoadKind.STRAIGHT,
            length=length,
            lanes=[
                Lane(id="lane_ego", center_y=0.0, width=3.5, direction=1),
                Lane(id="lane_adj", center_y=3.5, width=3.5, direction=1),
                Lane(id="lane_park", center_y=-3.5, width=3.0, direction=1),
            ],
        )
    return RoadLayout(
        kind=RoadKind.FOUR_WAY_INTERSECTION,
        length=length,
        lanes=[
            Lane(id="lane_eb", center_y=-1.75, width=3.5, direction=1),
            Lane(id="lane_wb", center_y=1.75, width=3.5, direction=-1),
            Lane(id="lane_adj", center_y=-5.25, width=3.5, direction=1),
        ],
        intersection_center=(40.0, 0.0),
        intersection_size=8.0,
    )


def _ego_lane_id(road_kind: RoadLayoutKind) -> str:
    return "lane_eb" if road_kind == RoadLayoutKind.FOUR_WAY else "lane_ego"


def _ego_y(road_kind: RoadLayoutKind) -> float:
    return -1.75 if road_kind == RoadLayoutKind.FOUR_WAY else 0.0


def _default_oracles() -> list[SafetyOracle]:
    return [
        SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
        SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=1.0),
        SafetyOracle(id="o_init", type=OracleType.NO_INITIAL_OVERLAP),
    ]


def build_seed_scene(
    *,
    example_id: str,
    family: ScenarioFamily,
    road_kind: RoadLayoutKind,
    actor_kind: ActorKind,
    trigger_kind: TriggerKind,
    variant: int,
) -> ScenarioSpec:
    """Build a benign seed scene; hazard activation is left to the mutation target."""
    del actor_kind  # composition metadata only
    length = 80.0
    road = build_road(road_kind, length=length)
    ego_lane = _ego_lane_id(road_kind)
    ego_y = _ego_y(road_kind)
    ego_speed = 10.0 + (variant % 3)

    ego = EgoVehicle(
        id="ego",
        actor_type="ego",
        position=Position2D(x=5.0, y=ego_y),
        velocity=Velocity2D(vx=ego_speed, vy=0.0),
        dimensions=Dimensions2D(length=4.5, width=1.8),
        lane_id=ego_lane,
        heading_deg=0.0,
        behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
    )

    actors: list = []
    triggers: list[Trigger] = []

    if family in {ScenarioFamily.OCCLUDED_PEDESTRIAN, ScenarioFamily.OCCLUDED_CYCLIST}:
        if road_kind == RoadLayoutKind.STRAIGHT_TRIPLE:
            park_y, park_lane = -3.5, "lane_park"
        else:
            park_y, park_lane = -3.5, None
        actors.append(
            VehicleActor(
                id="occluder",
                actor_type="vehicle",
                position=Position2D(x=32.0, y=park_y),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=5.0, width=2.0),
                lane_id=park_lane,
                heading_deg=0.0,
                behavior=ActorBehavior(type=BehaviorType.PARKED),
            )
        )
    elif family == ScenarioFamily.UNPROTECTED_LEFT:
        oncoming_lane = "lane_wb" if road_kind == RoadLayoutKind.FOUR_WAY else "lane_adj"
        oncoming_y = 1.75 if road_kind == RoadLayoutKind.FOUR_WAY else 3.5
        actors.append(
            VehicleActor(
                id="oncoming_seed",
                actor_type="vehicle",
                position=Position2D(x=70.0, y=oncoming_y),
                velocity=Velocity2D(vx=-5.0, vy=0.0),
                dimensions=Dimensions2D(length=4.5, width=1.8),
                lane_id=oncoming_lane,
                heading_deg=180.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            )
        )

    if trigger_kind == TriggerKind.TIME:
        triggers.append(Trigger(id="t_main", type=TriggerType.TIME, time_s=9.0))
    elif trigger_kind == TriggerKind.EGO_DISTANCE:
        triggers.append(
            Trigger(
                id="t_main",
                type=TriggerType.EGO_DISTANCE,
                distance_m=14.0,
                reference_point=Position2D(x=40.0, y=ego_y),
            )
        )
    elif trigger_kind == TriggerKind.EGO_ENTER_REGION:
        triggers.append(
            Trigger(
                id="t_main",
                type=TriggerType.EGO_ENTER_REGION,
                reference_point=Position2D(x=40.0, y=0.0),
                region_half_extent_m=8.0,
            )
        )

    return ScenarioSpec(
        id=f"seed_{example_id}",
        name=f"Seed for {family.value}",
        description=f"Benign seed scene for family={family.value} variant={variant}",
        duration_s=8.0,
        road=road,
        ego=ego,
        actors=actors,
        triggers=triggers,
        oracles=_default_oracles(),
        assumptions=list(DEFAULT_ASSUMPTIONS),
        unknowns=list(DEFAULT_UNKNOWNS),
    )
