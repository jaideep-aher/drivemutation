"""Six handwritten Stage-1 scenario presets."""

from __future__ import annotations

from backend.app.schemas.actors import CyclistActor, EgoVehicle, PedestrianActor, VehicleActor
from backend.app.schemas.behavior import ActorBehavior
from backend.app.schemas.common import (
    Assumption,
    BehaviorType,
    Dimensions2D,
    OracleType,
    Position2D,
    TriggerType,
    Unknown,
    Velocity2D,
)
from backend.app.schemas.oracles import SafetyOracle
from backend.app.schemas.road import Lane, RoadKind, RoadLayout
from backend.app.schemas.scenario import PresetSummary, ScenarioSpec
from backend.app.schemas.triggers import Trigger

DEFAULT_ASSUMPTIONS = [
    Assumption(
        id="a_si",
        statement="All quantities are SI: m, s, m/s, m/s².",
    ),
    Assumption(
        id="a_dt",
        statement="Integration uses a fixed 0.1 s timestep with constant-velocity segments.",
    ),
    Assumption(
        id="a_2d",
        statement="World is planar 2D; no elevation, weather, or sensor noise.",
    ),
]

DEFAULT_UNKNOWNS = [
    Unknown(
        id="u_perception",
        statement="Perception latency and false negatives are out of scope in Stage 1.",
    ),
    Unknown(
        id="u_control",
        statement="Ego follows scripted velocity; no AV planner or controller is modelled.",
    ),
]


def _straight_road(length: float = 80.0) -> RoadLayout:
    return RoadLayout(
        kind=RoadKind.STRAIGHT,
        length=length,
        lanes=[
            Lane(id="lane_ego", center_y=0.0, width=3.5, direction=1),
            Lane(id="lane_opp", center_y=3.5, width=3.5, direction=-1),
            Lane(id="lane_park", center_y=-3.5, width=3.0, direction=1),
        ],
    )


def _intersection_road(length: float = 80.0) -> RoadLayout:
    return RoadLayout(
        kind=RoadKind.FOUR_WAY_INTERSECTION,
        length=length,
        lanes=[
            Lane(id="lane_eb", center_y=-1.75, width=3.5, direction=1),
            Lane(id="lane_wb", center_y=1.75, width=3.5, direction=-1),
            Lane(id="lane_nb", center_y=0.0, width=3.5, direction=1),  # used as lateral ref
        ],
        intersection_center=(40.0, 0.0),
        intersection_size=8.0,
        cross_lane_width=3.5,
    )


def occluded_pedestrian() -> ScenarioSpec:
    return ScenarioSpec(
        id="occluded_pedestrian",
        name="Occluded pedestrian",
        description=(
            "Ego drives east; a parked van occludes a pedestrian who enters the "
            "crosswalk when ego is nearby."
        ),
        duration_s=8.0,
        road=_straight_road(70.0),
        ego=EgoVehicle(
            id="ego",
            actor_type="ego",
            position=Position2D(x=5.0, y=0.0),
            velocity=Velocity2D(vx=12.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id="lane_ego",
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        ),
        actors=[
            VehicleActor(
                id="parked_van",
                actor_type="vehicle",
                position=Position2D(x=32.0, y=-3.5),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=5.0, width=2.0),
                lane_id="lane_park",
                heading_deg=0.0,
                behavior=ActorBehavior(type=BehaviorType.PARKED),
            ),
            PedestrianActor(
                id="ped",
                actor_type="pedestrian",
                position=Position2D(x=38.0, y=-6.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=0.6, width=0.6),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CROSSING,
                    trigger_id="near_crosswalk",
                    post_trigger_velocity=Velocity2D(vx=0.0, vy=1.5),
                ),
            ),
        ],
        triggers=[
            Trigger(
                id="near_crosswalk",
                type=TriggerType.EGO_DISTANCE,
                distance_m=12.0,
                reference_point=Position2D(x=38.0, y=0.0),
            )
        ],
        oracles=[
            SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
            SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=1.0),
            SafetyOracle(id="o_init", type=OracleType.NO_INITIAL_OVERLAP),
        ],
        assumptions=DEFAULT_ASSUMPTIONS,
        unknowns=DEFAULT_UNKNOWNS,
    )


def occluded_cyclist() -> ScenarioSpec:
    return ScenarioSpec(
        id="occluded_cyclist",
        name="Occluded cyclist",
        description=(
            "A parked truck occludes a cyclist who crosses the ego lane after a time trigger."
        ),
        duration_s=8.0,
        road=_straight_road(70.0),
        ego=EgoVehicle(
            id="ego",
            actor_type="ego",
            position=Position2D(x=4.0, y=0.0),
            velocity=Velocity2D(vx=11.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id="lane_ego",
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        ),
        actors=[
            VehicleActor(
                id="parked_truck",
                actor_type="vehicle",
                position=Position2D(x=28.0, y=-3.5),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=6.0, width=2.2),
                lane_id="lane_park",
                heading_deg=0.0,
                behavior=ActorBehavior(type=BehaviorType.PARKED),
            ),
            CyclistActor(
                id="cyclist",
                actor_type="cyclist",
                position=Position2D(x=34.0, y=-7.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=1.8, width=0.7),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CROSSING,
                    trigger_id="t_cross",
                    post_trigger_velocity=Velocity2D(vx=0.0, vy=4.0),
                ),
            ),
        ],
        triggers=[Trigger(id="t_cross", type=TriggerType.TIME, time_s=2.0)],
        oracles=[
            SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
            SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=1.2),
        ],
        assumptions=DEFAULT_ASSUMPTIONS,
        unknowns=DEFAULT_UNKNOWNS,
    )


def aggressive_cut_in() -> ScenarioSpec:
    return ScenarioSpec(
        id="aggressive_cut_in",
        name="Aggressive cut-in",
        description="Adjacent vehicle cuts into the ego lane at short range.",
        duration_s=6.0,
        road=_straight_road(80.0),
        ego=EgoVehicle(
            id="ego",
            actor_type="ego",
            position=Position2D(x=10.0, y=0.0),
            velocity=Velocity2D(vx=15.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id="lane_ego",
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        ),
        actors=[
            VehicleActor(
                id="cutter",
                actor_type="vehicle",
                position=Position2D(x=22.0, y=3.5),
                velocity=Velocity2D(vx=16.0, vy=0.0),
                dimensions=Dimensions2D(length=4.4, width=1.8),
                lane_id="lane_opp",
                heading_deg=0.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CUT_IN,
                    trigger_id="t_cut",
                    post_trigger_velocity=Velocity2D(vx=15.0, vy=0.0),
                    target_lane_id="lane_ego",
                    lateral_speed=3.0,
                ),
            ),
        ],
        triggers=[Trigger(id="t_cut", type=TriggerType.TIME, time_s=0.8)],
        oracles=[
            SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
            SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=0.8),
            SafetyOracle(id="o_lane", type=OracleType.LANE_KEEPING),
        ],
        assumptions=DEFAULT_ASSUMPTIONS,
        unknowns=DEFAULT_UNKNOWNS,
    )


def unprotected_left_turn() -> ScenarioSpec:
    return ScenarioSpec(
        id="unprotected_left_turn",
        name="Unprotected left turn",
        description=(
            "Ego proceeds through a four-way intersection while an oncoming vehicle "
            "continues straight (conflict on the intersection box)."
        ),
        duration_s=7.0,
        road=_intersection_road(80.0),
        ego=EgoVehicle(
            id="ego",
            actor_type="ego",
            position=Position2D(x=20.0, y=-1.75),
            velocity=Velocity2D(vx=8.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id="lane_eb",
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        ),
        actors=[
            VehicleActor(
                id="oncoming",
                actor_type="vehicle",
                position=Position2D(x=58.0, y=1.75),
                velocity=Velocity2D(vx=-10.0, vy=0.0),
                dimensions=Dimensions2D(length=4.5, width=1.8),
                lane_id="lane_wb",
                heading_deg=180.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            ),
            # Cross-traffic that starts when ego enters intersection region
            VehicleActor(
                id="cross_traffic",
                actor_type="vehicle",
                position=Position2D(x=40.0, y=-18.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=4.5, width=1.8),
                lane_id=None,
                heading_deg=90.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CROSSING,
                    trigger_id="enter_box",
                    post_trigger_velocity=Velocity2D(vx=0.0, vy=9.0),
                ),
            ),
        ],
        triggers=[
            Trigger(
                id="enter_box",
                type=TriggerType.EGO_ENTER_REGION,
                reference_point=Position2D(x=40.0, y=0.0),
                region_half_extent_m=8.0,
            )
        ],
        oracles=[
            SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
            SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=1.5),
        ],
        assumptions=DEFAULT_ASSUMPTIONS
        + [
            Assumption(
                id="a_turn",
                statement=(
                    "Stage 1 approximates the unprotected left as constant-velocity "
                    "conflict geometry; curved turning paths are deferred."
                ),
            )
        ],
        unknowns=DEFAULT_UNKNOWNS,
    )


def construction_lane_closure() -> ScenarioSpec:
    return ScenarioSpec(
        id="construction_lane_closure",
        name="Construction lane closure",
        description=(
            "Ego lane is blocked by a stationary construction vehicle; a merge cut-in "
            "from the adjacent lane models forced lane change pressure."
        ),
        duration_s=8.0,
        road=_straight_road(90.0),
        ego=EgoVehicle(
            id="ego",
            actor_type="ego",
            position=Position2D(x=5.0, y=0.0),
            velocity=Velocity2D(vx=10.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id="lane_ego",
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        ),
        actors=[
            VehicleActor(
                id="construction_blocker",
                actor_type="vehicle",
                position=Position2D(x=45.0, y=0.0),
                velocity=Velocity2D(vx=0.0, vy=0.0),
                dimensions=Dimensions2D(length=6.0, width=2.2),
                lane_id="lane_ego",
                heading_deg=0.0,
                behavior=ActorBehavior(type=BehaviorType.PARKED),
            ),
            VehicleActor(
                id="merge_vehicle",
                actor_type="vehicle",
                position=Position2D(x=20.0, y=3.5),
                velocity=Velocity2D(vx=11.0, vy=0.0),
                dimensions=Dimensions2D(length=4.4, width=1.8),
                lane_id="lane_opp",
                heading_deg=0.0,
                behavior=ActorBehavior(
                    type=BehaviorType.TRIGGERED_CUT_IN,
                    trigger_id="t_merge",
                    post_trigger_velocity=Velocity2D(vx=10.0, vy=0.0),
                    target_lane_id="lane_ego",
                    lateral_speed=2.5,
                ),
            ),
        ],
        triggers=[Trigger(id="t_merge", type=TriggerType.TIME, time_s=1.5)],
        oracles=[
            SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
            SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=1.0),
            SafetyOracle(id="o_init", type=OracleType.NO_INITIAL_OVERLAP),
        ],
        assumptions=DEFAULT_ASSUMPTIONS
        + [
            Assumption(
                id="a_cones",
                statement="Construction zone is represented by a parked blocking vehicle only.",
            )
        ],
        unknowns=DEFAULT_UNKNOWNS,
    )


def wrong_way_vehicle() -> ScenarioSpec:
    return ScenarioSpec(
        id="wrong_way_vehicle",
        name="Wrong-way vehicle",
        description="An opposing vehicle travels the wrong way in the ego lane.",
        duration_s=6.0,
        road=_straight_road(80.0),
        ego=EgoVehicle(
            id="ego",
            actor_type="ego",
            position=Position2D(x=5.0, y=0.0),
            velocity=Velocity2D(vx=12.0, vy=0.0),
            dimensions=Dimensions2D(length=4.5, width=1.8),
            lane_id="lane_ego",
            heading_deg=0.0,
            behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
        ),
        actors=[
            VehicleActor(
                id="wrong_way",
                actor_type="vehicle",
                position=Position2D(x=60.0, y=0.0),
                velocity=Velocity2D(vx=-14.0, vy=0.0),
                dimensions=Dimensions2D(length=4.5, width=1.8),
                lane_id="lane_ego",
                heading_deg=180.0,
                behavior=ActorBehavior(type=BehaviorType.CONSTANT_VELOCITY),
            ),
        ],
        triggers=[],
        oracles=[
            SafetyOracle(id="o_collision", type=OracleType.NO_COLLISION),
            SafetyOracle(id="o_ttc", type=OracleType.MIN_TTC, threshold=2.0),
        ],
        assumptions=DEFAULT_ASSUMPTIONS,
        unknowns=DEFAULT_UNKNOWNS
        + [
            Unknown(
                id="u_intent",
                statement="Intent of the wrong-way driver is unknown; motion is scripted.",
            )
        ],
    )


PRESET_BUILDERS = {
    "occluded_pedestrian": occluded_pedestrian,
    "occluded_cyclist": occluded_cyclist,
    "aggressive_cut_in": aggressive_cut_in,
    "unprotected_left_turn": unprotected_left_turn,
    "construction_lane_closure": construction_lane_closure,
    "wrong_way_vehicle": wrong_way_vehicle,
}


def list_presets() -> list[PresetSummary]:
    out: list[PresetSummary] = []
    for builder in PRESET_BUILDERS.values():
        sc = builder()
        out.append(PresetSummary(id=sc.id, name=sc.name, description=sc.description))
    return out


def get_preset(preset_id: str) -> ScenarioSpec:
    if preset_id not in PRESET_BUILDERS:
        raise KeyError(preset_id)
    return PRESET_BUILDERS[preset_id]()


def all_presets() -> list[ScenarioSpec]:
    return [b() for b in PRESET_BUILDERS.values()]
