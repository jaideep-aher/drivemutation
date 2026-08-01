"""Logical scenarios from NHTSA, UNECE R157, Euro NCAP and HAZOP derivation.

The NHTSA portion is the complete pre-crash scenario typology.  Najm, Smith &
Yanagisawa, *Pre-Crash Scenario Typology for Crash Avoidance Research*
(DOT HS 810 767, 2007) enumerates 37 scenarios "including other"; scenario 37 is
a residual bucket worth 0.6% of crashes, so the 36 substantive scenarios are
what appears here.  Scenario names, crash counts and shares come from
``data/typology/nhtsa_precrash_typology.json``, which was transcribed
independently by two researchers from the primary PDFs — the table below is
checked against that file by ``tests/test_catalog.py``, so the two cannot drift.

Group assignments follow the nine crash groups of Swanson et al., *Statistics of
Light-Vehicle Pre-Crash Scenarios Based on 2011-2015 National Crash Data*
(DOT HS 812 745, 2019).  Scenarios outside those nine — vehicle failure,
backing, object, evasive action, non-collision — are what NHTSA counts as
"remaining scenarios".

Three modelling conventions, applied consistently and worth stating because they
are judgement calls, not facts from the reports:

**Single-vehicle scenarios are re-cast around the ego as the system under test.**
The typology describes what the *subject* vehicle does, so "control loss" means
the subject skids.  Testing that the ego skids exercises vehicle dynamics, not an
automated driving system.  Where the hazard is another road user's loss of
control, failure or evasive manoeuvre, the principal other vehicle carries the
behaviour and the ego has something to detect and respond to.  Road-edge
departure is the exception: there the ego really does drift, toward a static
roadside object.

**Backing is modelled as a low-speed closing conflict.**  The kinematic layer has
no gear model, and the criticality of a reversing conflict is set by closing
speed and gap, which are identical whether the gear is forward or reverse.  These
scenarios therefore run at 5-15 km/h with the conflict ahead in the direction of
travel.

**Parameter ranges are engineering judgement.**  The reports give crash
frequencies, not speed distributions.  Ranges here are plausible rather than
fitted, which is exactly what Stage 5 exists to replace; every entry says so in
its provenance notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.signalforge.schema import (
    ActorSpec,
    Lighting,
    LogicalScenario,
    ParamRange,
    Provenance,
    RoadGeometry,
    ScenarioFamily,
    SourceType,
    Weather,
)

_PRIMARY = "NHTSA DOT HS 810 767 (2007)"
_STATS = "DOT HS 812 745 (2019)"
_RANGE_NOTE = (
    "Parameter ranges are engineering judgement, not fitted from crash data; "
    "the published figures are the crash counts and shares."
)

# Scenario number -> (published name, 2019 crash group, annual crashes, share %).
# Verified against data/typology/nhtsa_precrash_typology.json by the tests.
_NHTSA_FACTS: dict[int, tuple[str, str, int, float]] = {
    1: ("Vehicle Failure", "vehicle failure", 42000, 0.71),
    2: ("Control Loss With Prior Vehicle Action", "control loss", 103000, 1.73),
    3: ("Control Loss Without Prior Vehicle Action", "control loss", 529000, 8.9),
    4: ("Running Red Light", "crossing paths", 254000, 4.27),
    5: ("Running Stop Sign", "crossing paths", 48000, 0.81),
    6: ("Road Edge Departure With Prior Vehicle Maneuver", "road departure", 68000, 1.14),
    7: ("Road Edge Departure Without Prior Vehicle Maneuver", "road departure", 334000, 5.62),
    8: ("Road Edge Departure While Backing Up", "backing", 66000, 1.11),
    9: ("Animal Crash With Prior Vehicle Maneuver", "animal", 23000, 0.39),
    10: ("Animal Crash Without Prior Vehicle Maneuver", "animal", 305000, 5.13),
    11: ("Pedestrian Crash With Prior Vehicle Maneuver", "pedestrian", 17000, 0.29),
    12: ("Pedestrian Crash Without Prior Vehicle Maneuver", "pedestrian", 39000, 0.66),
    13: ("Pedalcyclist Crash With Prior Vehicle Maneuver", "pedalcyclist", 18000, 0.31),
    14: ("Pedalcyclist Crash Without Prior Vehicle Maneuver", "pedalcyclist", 24000, 0.41),
    15: ("Backing Up Into Another Vehicle", "backing", 131000, 2.2),
    16: ("Vehicle(s) Turning – Same Direction", "lane change", 222000, 3.73),
    17: ("Vehicle(s) Parking – Same Direction", "lane change", 48000, 0.81),
    18: ("Vehicle(s) Changing Lanes – Same Direction", "lane change", 338000, 5.69),
    19: ("Vehicle(s) Drifting – Same Direction", "lane change", 98000, 1.65),
    20: ("Vehicle(s) Making a Maneuver – Opposite Direction", "opposite direction", 15000, 0.26),
    21: (
        "Vehicle(s) Not Making a Maneuver – Opposite Direction",
        "opposite direction",
        124000,
        2.08,
    ),
    22: ("Following Vehicle Making a Maneuver", "rear-end", 85000, 1.44),
    23: ("Lead Vehicle Accelerating", "rear-end", 19000, 0.32),
    24: ("Lead Vehicle Moving at Lower Constant Speed", "rear-end", 210000, 3.53),
    25: ("Lead Vehicle Decelerating", "rear-end", 428000, 7.2),
    26: ("Lead Vehicle Stopped", "rear-end", 975000, 16.41),
    27: (
        "Left Turn Across Path From Opposite Directions at Signalized Junctions",
        "crossing paths",
        220000,
        3.71,
    ),
    28: ("Vehicle Turning Right at Signalized Junctions", "crossing paths", 35000, 0.59),
    29: (
        "Left Turn Across Path From Opposite Directions at Non-Signalized Junctions",
        "crossing paths",
        190000,
        3.19,
    ),
    30: ("Straight Crossing Paths at Non-Signalized Junctions", "crossing paths", 264000, 4.44),
    31: ("Vehicle(s) Turning at Non-Signalized Junctions", "crossing paths", 435000, 7.32),
    32: ("Evasive Action With Prior Vehicle Maneuver", "evasive action", 13000, 0.22),
    33: ("Evasive Action Without Prior Vehicle Maneuver", "evasive action", 56000, 0.95),
    34: ("Non-Collision Incident", "non-collision", 46000, 0.77),
    35: ("Object Crash With Prior Vehicle Maneuver", "object", 30000, 0.51),
    36: ("Object Crash Without Prior Vehicle Maneuver", "object", 55000, 0.92),
}

#: The most frequent scenario (26, Lead Vehicle Stopped) anchors the weight
#: scale at 1.0, so every weight is a published share rather than a guess.
_MAX_SHARE_PCT = max(share for *_, share in _NHTSA_FACTS.values())


def _vehicle(role: str, behavior: str = "constant_velocity") -> ActorSpec:
    return ActorSpec(actor_type="vehicle", role=role, behavior=behavior)


def _pedestrian(role: str, behavior: str = "cross") -> ActorSpec:
    return ActorSpec(
        actor_type="pedestrian",
        role=role,
        length_m=0.6,
        width_m=0.6,
        height_m=1.7,
        behavior=behavior,
    )


def _cyclist(role: str, behavior: str = "cross") -> ActorSpec:
    return ActorSpec(
        actor_type="cyclist",
        role=role,
        length_m=1.8,
        width_m=0.6,
        height_m=1.7,
        behavior=behavior,
    )


def _animal(role: str = "crossing", behavior: str = "cross") -> ActorSpec:
    return ActorSpec(
        actor_type="animal",
        role=role,
        length_m=2.0,
        width_m=0.8,
        height_m=1.4,
        behavior=behavior,
    )


def _obstacle(role: str, length: float = 2.0, width: float = 1.5, height: float = 1.0) -> ActorSpec:
    return ActorSpec(
        actor_type="static",
        role=role,
        length_m=length,
        width_m=width,
        height_m=height,
        behavior="static",
    )


@dataclass(frozen=True)
class _Spec:
    """How one typology scenario is turned into a parameterised logical scenario."""

    slug: str
    family: ScenarioFamily
    description: str
    roads: list[RoadGeometry]
    weathers: list[Weather]
    lightings: list[Lighting]
    ego_kph: tuple[float, float]
    actor_kph: tuple[float, float]
    distance_m: tuple[float, float]
    actors: list[ActorSpec]
    odd: dict = field(default_factory=dict)
    ttc_s: tuple[float, float] | None = None
    notes: str = ""
    simulable: bool = True


_ALL_WEATHER = [Weather.CLEAR, Weather.RAIN, Weather.FOG]
_DAY_NIGHT = [Lighting.DAY, Lighting.NIGHT]
_ALL_LIGHT = [Lighting.DAY, Lighting.DUSK, Lighting.NIGHT]
_URBAN = [RoadGeometry.STRAIGHT, RoadGeometry.INTERSECTION]
_OPEN = [RoadGeometry.STRAIGHT, RoadGeometry.HIGHWAY]
_CURVY = [RoadGeometry.STRAIGHT, RoadGeometry.CURVE]

_NHTSA_SPECS: dict[int, _Spec] = {
    1: _Spec(
        slug="vehicle-failure",
        family=ScenarioFamily.VEHICLE_FAILURE,
        description=(
            "A vehicle ahead suffers a component failure (blowout, shed load) and "
            "becomes an obstacle in the ego path."
        ),
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_DAY_NIGHT,
        ego_kph=(60, 120),
        actor_kph=(0, 0),
        distance_m=(25, 90),
        actors=[_obstacle("failed_vehicle", length=4.5, width=1.9, height=1.5)],
        odd={"debris_size_m": [0.5, 1.0, 2.0]},
        notes=(
            "The typology describes the subject vehicle failing. Re-cast onto a "
            "principal other vehicle so the ego has a hazard to perceive."
        ),
    ),
    2: _Spec(
        slug="control-loss-with-prior-action",
        family=ScenarioFamily.CONTROL_LOSS,
        description="A vehicle loses control during a manoeuvre and swerves into the ego path.",
        roads=_CURVY,
        weathers=[Weather.RAIN, Weather.SNOW, Weather.CLEAR],
        lightings=_DAY_NIGHT,
        ego_kph=(40, 100),
        actor_kph=(25, 70),
        distance_m=(15, 60),
        actors=[_vehicle("unstable", "swerve")],
        odd={"surface": ["wet", "ice", "dry"], "prior_action": ["turning", "braking"]},
        notes="Control loss carried by the other vehicle; see module docstring.",
    ),
    3: _Spec(
        slug="control-loss-without-prior-action",
        family=ScenarioFamily.CONTROL_LOSS,
        description="A vehicle going straight or on a curve loses control into the ego path.",
        roads=_CURVY,
        weathers=[Weather.RAIN, Weather.SNOW, Weather.CLEAR],
        lightings=_DAY_NIGHT,
        ego_kph=(40, 110),
        actor_kph=(25, 75),
        distance_m=(15, 70),
        actors=[_vehicle("unstable", "swerve")],
        odd={"surface": ["wet", "ice", "dry"]},
        notes="Control loss carried by the other vehicle; see module docstring.",
    ),
    4: _Spec(
        slug="running-red-light",
        family=ScenarioFamily.CROSSING_PATHS,
        description="A vehicle enters a signalised junction against a red light across the ego path.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 70),
        actor_kph=(30, 70),
        distance_m=(15, 55),
        actors=[_vehicle("violator", "left_turn")],
        odd={"signal_state": ["green", "yellow"], "occlusion": ["none", "partial"]},
    ),
    5: _Spec(
        slug="running-stop-sign",
        family=ScenarioFamily.CROSSING_PATHS,
        description="A vehicle fails to stop at a stop-controlled junction across the ego path.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 60),
        actor_kph=(20, 55),
        distance_m=(12, 45),
        actors=[_vehicle("violator", "left_turn")],
        odd={"occlusion": ["none", "partial", "full"]},
    ),
    6: _Spec(
        slug="road-edge-departure-with-prior-maneuver",
        family=ScenarioFamily.ROAD_DEPARTURE,
        description="The ego departs the road edge during a manoeuvre toward a roadside object.",
        roads=_CURVY,
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.SNOW],
        lightings=_DAY_NIGHT,
        ego_kph=(50, 110),
        actor_kph=(0, 0),
        distance_m=(15, 60),
        actors=[_obstacle("roadside_object", length=12.0, width=0.5, height=1.0)],
        odd={"surface": ["dry", "wet", "ice"], "prior_action": ["turning", "avoiding"]},
    ),
    7: _Spec(
        slug="road-edge-departure-without-prior-maneuver",
        family=ScenarioFamily.ROAD_DEPARTURE,
        description="The ego drifts off the road edge while going straight or on a curve.",
        roads=[RoadGeometry.STRAIGHT, RoadGeometry.CURVE, RoadGeometry.HIGHWAY],
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.SNOW],
        lightings=_DAY_NIGHT,
        ego_kph=(50, 120),
        actor_kph=(0, 0),
        distance_m=(15, 70),
        actors=[_obstacle("roadside_object", length=20.0, width=0.5, height=1.0)],
        odd={"surface": ["dry", "wet", "ice"]},
    ),
    8: _Spec(
        slug="road-edge-departure-backing",
        family=ScenarioFamily.BACKING,
        description="The ego reverses toward the road edge and a roadside obstruction.",
        roads=[RoadGeometry.STRAIGHT],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(5, 15),
        actor_kph=(0, 0),
        distance_m=(10, 25),
        actors=[_obstacle("roadside_object", length=6.0, width=0.6, height=1.2)],
        odd={"occlusion": ["none", "partial", "full"]},
        notes="Reverse gear modelled as low-speed closing motion; see module docstring.",
    ),
    9: _Spec(
        slug="animal-with-prior-maneuver",
        family=ScenarioFamily.ANIMAL,
        description="An animal enters the ego path while the ego is mid-manoeuvre.",
        roads=[RoadGeometry.STRAIGHT, RoadGeometry.CURVE],
        weathers=[Weather.CLEAR, Weather.FOG],
        lightings=[Lighting.NIGHT, Lighting.DAWN, Lighting.DUSK],
        ego_kph=(40, 90),
        actor_kph=(5, 35),
        distance_m=(15, 55),
        actors=[_animal()],
        odd={"animal_size": ["deer", "dog", "livestock"], "prior_action": ["turning"]},
    ),
    10: _Spec(
        slug="animal-without-prior-maneuver",
        family=ScenarioFamily.ANIMAL,
        description="An animal enters the roadway ahead of the ego travelling straight.",
        roads=[RoadGeometry.STRAIGHT, RoadGeometry.HIGHWAY, RoadGeometry.CURVE],
        weathers=[Weather.CLEAR, Weather.FOG],
        lightings=[Lighting.NIGHT, Lighting.DAWN, Lighting.DUSK],
        ego_kph=(50, 110),
        actor_kph=(5, 40),
        distance_m=(15, 60),
        actors=[_animal()],
        odd={"animal_size": ["deer", "dog", "livestock"]},
    ),
    11: _Spec(
        slug="pedestrian-with-prior-maneuver",
        family=ScenarioFamily.PEDESTRIAN,
        description="A pedestrian enters the path of the ego while it is turning.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(10, 35),
        actor_kph=(3, 8),
        distance_m=(6, 25),
        actors=[_pedestrian("crossing")],
        odd={"occlusion": ["none", "partial"], "turn": ["left", "right"]},
    ),
    12: _Spec(
        slug="pedestrian-without-prior-maneuver",
        family=ScenarioFamily.PEDESTRIAN,
        description="A pedestrian enters the roadway ahead of the ego travelling straight.",
        roads=_URBAN,
        weathers=_ALL_WEATHER,
        lightings=_ALL_LIGHT,
        ego_kph=(20, 60),
        actor_kph=(3, 8),
        distance_m=(8, 35),
        actors=[_pedestrian("crossing")],
        odd={"occlusion": ["none", "partial", "full"], "jaywalk": [True, False]},
    ),
    13: _Spec(
        slug="pedalcyclist-with-prior-maneuver",
        family=ScenarioFamily.PEDALCYCLIST,
        description="A cyclist crosses the path of the ego while it is turning.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=[Lighting.DAY, Lighting.DUSK],
        ego_kph=(10, 40),
        actor_kph=(10, 25),
        distance_m=(8, 30),
        actors=[_cyclist("crossing")],
        odd={"occlusion": ["none", "partial"], "turn": ["left", "right"]},
    ),
    14: _Spec(
        slug="pedalcyclist-without-prior-maneuver",
        family=ScenarioFamily.PEDALCYCLIST,
        description="A cyclist crosses or rides into the path of the ego travelling straight.",
        roads=_URBAN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=[Lighting.DAY, Lighting.DUSK],
        ego_kph=(25, 60),
        actor_kph=(10, 30),
        distance_m=(10, 40),
        actors=[_cyclist("crossing")],
        odd={"occlusion": ["none", "partial"]},
    ),
    15: _Spec(
        slug="backing-into-vehicle",
        family=ScenarioFamily.BACKING,
        description="The ego reverses into the path of another vehicle behind it.",
        roads=[RoadGeometry.STRAIGHT],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(5, 15),
        actor_kph=(0, 0),
        distance_m=(8, 25),
        actors=[_vehicle("behind", "static")],
        odd={"occlusion": ["none", "partial", "full"]},
        notes="Reverse gear modelled as low-speed closing motion; see module docstring.",
    ),
    16: _Spec(
        slug="turning-same-direction",
        family=ScenarioFamily.LANE_CHANGE,
        description="A same-direction vehicle turns across the ego path.",
        roads=_URBAN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 80),
        actor_kph=(20, 70),
        distance_m=(8, 35),
        actors=[_vehicle("turning", "cut_in")],
        odd={"lane_count": [2, 3], "turn": ["left", "right"]},
    ),
    17: _Spec(
        slug="parking-same-direction",
        family=ScenarioFamily.LANE_CHANGE,
        description="A vehicle pulls out of or into a parking position across the ego path.",
        roads=[RoadGeometry.STRAIGHT],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(20, 55),
        actor_kph=(5, 25),
        distance_m=(6, 25),
        actors=[_vehicle("parking", "cut_in")],
        odd={"lane_count": [2, 3], "occlusion": ["none", "partial"]},
    ),
    18: _Spec(
        slug="changing-lanes-same-direction",
        family=ScenarioFamily.LANE_CHANGE,
        description="An adjacent vehicle changes deliberately into the ego lane.",
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(50, 120),
        actor_kph=(35, 95),
        distance_m=(5, 30),
        actors=[_vehicle("adjacent", "cut_in")],
        odd={"lane_count": [2, 3, 4]},
    ),
    19: _Spec(
        slug="drifting-same-direction",
        family=ScenarioFamily.LANE_CHANGE,
        description="An adjacent vehicle drifts out of its lane into the ego.",
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(50, 120),
        actor_kph=(30, 90),
        distance_m=(5, 30),
        actors=[_vehicle("adjacent", "cut_in")],
        odd={"lane_count": [2, 3], "drift_rate_mps": [0.2, 0.5, 0.9]},
    ),
    20: _Spec(
        slug="opposite-direction-with-maneuver",
        family=ScenarioFamily.OPPOSITE_DIRECTION,
        description="An oncoming vehicle manoeuvres across the centreline into the ego lane.",
        roads=_CURVY,
        weathers=_ALL_WEATHER,
        lightings=_DAY_NIGHT,
        ego_kph=(40, 100),
        actor_kph=(40, 100),
        distance_m=(30, 120),
        actors=[_vehicle("oncoming", "encroach")],
        odd={"encroach_m": [0.5, 1.0, 1.5, 2.0], "prior_action": ["overtaking", "turning"]},
    ),
    21: _Spec(
        slug="opposite-direction-without-maneuver",
        family=ScenarioFamily.OPPOSITE_DIRECTION,
        description="An oncoming vehicle drifts across the centreline into the ego lane.",
        roads=_CURVY,
        weathers=_ALL_WEATHER,
        lightings=_DAY_NIGHT,
        ego_kph=(40, 100),
        actor_kph=(40, 100),
        distance_m=(30, 120),
        actors=[_vehicle("oncoming", "encroach")],
        odd={"encroach_m": [0.5, 1.0, 1.5, 2.0]},
    ),
    22: _Spec(
        slug="following-vehicle-making-maneuver",
        family=ScenarioFamily.REAR_END,
        description="The ego closes on a lead vehicle after changing lanes or overtaking.",
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(50, 120),
        actor_kph=(30, 90),
        distance_m=(10, 50),
        actors=[_vehicle("lead", "constant_velocity")],
        ttc_s=(1.0, 4.0),
        odd={"lane_count": [2, 3]},
    ),
    23: _Spec(
        slug="lead-vehicle-accelerating",
        family=ScenarioFamily.REAR_END,
        description="The ego closes on a lead vehicle that is accelerating away.",
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(40, 110),
        actor_kph=(15, 70),
        distance_m=(10, 45),
        actors=[_vehicle("lead", "accelerate")],
        ttc_s=(1.2, 4.0),
        odd={"lead_accel_mps2": [1.0, 2.0, 3.0]},
    ),
    24: _Spec(
        slug="lead-vehicle-lower-constant-speed",
        family=ScenarioFamily.REAR_END,
        description="The ego closes on a lead vehicle travelling at a lower constant speed.",
        roads=_OPEN,
        weathers=_ALL_WEATHER,
        lightings=_ALL_LIGHT,
        ego_kph=(50, 120),
        actor_kph=(20, 80),
        distance_m=(10, 55),
        actors=[_vehicle("lead", "constant_velocity")],
        ttc_s=(1.0, 4.0),
        odd={"occlusion": ["none", "partial"]},
    ),
    25: _Spec(
        slug="lead-vehicle-decelerating",
        family=ScenarioFamily.REAR_END,
        description="The ego follows a lead vehicle that suddenly brakes.",
        roads=_OPEN,
        weathers=_ALL_WEATHER,
        lightings=_ALL_LIGHT,
        ego_kph=(40, 110),
        actor_kph=(0, 100),
        distance_m=(8, 60),
        actors=[_vehicle("lead", "brake")],
        ttc_s=(0.8, 4.0),
        odd={"occlusion": ["none", "partial"], "lead_decel_mps2": [3, 5, 7, 9]},
    ),
    26: _Spec(
        slug="lead-vehicle-stopped",
        family=ScenarioFamily.REAR_END,
        description="The ego closes on a stationary vehicle in its own lane.",
        roads=_OPEN,
        weathers=_ALL_WEATHER,
        lightings=_ALL_LIGHT,
        ego_kph=(40, 110),
        actor_kph=(0, 0),
        distance_m=(15, 80),
        actors=[_vehicle("lead", "static")],
        odd={"occlusion": ["none", "partial", "full"]},
    ),
    27: _Spec(
        slug="ltap-opposite-direction-signalized",
        family=ScenarioFamily.CROSSING_PATHS,
        description="An oncoming vehicle turns left across the ego path at a signal.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 70),
        actor_kph=(15, 45),
        distance_m=(12, 45),
        actors=[_vehicle("turning", "left_turn")],
        odd={"signal_state": ["green", "yellow"], "occlusion": ["none", "partial"]},
    ),
    28: _Spec(
        slug="turning-right-signalized",
        family=ScenarioFamily.CROSSING_PATHS,
        description="A vehicle turning right at a signal enters the ego path.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(25, 60),
        actor_kph=(10, 35),
        distance_m=(10, 40),
        actors=[_vehicle("turning", "left_turn")],
        odd={"signal_state": ["green", "red"]},
    ),
    29: _Spec(
        slug="ltap-opposite-direction-non-signalized",
        family=ScenarioFamily.CROSSING_PATHS,
        description="An oncoming vehicle turns left across the ego path at an unsignalised junction.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 70),
        actor_kph=(15, 45),
        distance_m=(12, 45),
        actors=[_vehicle("turning", "left_turn")],
        odd={"occlusion": ["none", "partial", "full"]},
    ),
    30: _Spec(
        slug="straight-crossing-paths-non-signalized",
        family=ScenarioFamily.CROSSING_PATHS,
        description="A vehicle crosses straight through an unsignalised junction into the ego path.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 70),
        actor_kph=(20, 60),
        distance_m=(12, 50),
        actors=[_vehicle("crossing", "left_turn")],
        odd={"occlusion": ["none", "partial", "full"]},
    ),
    31: _Spec(
        slug="turning-non-signalized",
        family=ScenarioFamily.CROSSING_PATHS,
        description="A vehicle turns from a stop into laterally crossing ego traffic.",
        roads=[RoadGeometry.INTERSECTION],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(30, 70),
        actor_kph=(10, 45),
        distance_m=(10, 45),
        actors=[_vehicle("turning", "left_turn")],
        odd={"occlusion": ["none", "partial"], "turn": ["left", "right"]},
    ),
    32: _Spec(
        slug="evasive-action-with-prior-maneuver",
        family=ScenarioFamily.EVASIVE_ACTION,
        description=(
            "A vehicle mid-manoeuvre swerves to avoid an obstacle and enters the ego path."
        ),
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_ALL_LIGHT,
        ego_kph=(50, 110),
        actor_kph=(30, 80),
        distance_m=(15, 60),
        actors=[_vehicle("evading", "swerve")],
        odd={"lane_count": [2, 3], "prior_action": ["overtaking", "turning"]},
        notes="Evasive action carried by the other vehicle; see module docstring.",
    ),
    33: _Spec(
        slug="evasive-action-without-prior-maneuver",
        family=ScenarioFamily.EVASIVE_ACTION,
        description="A vehicle going straight swerves to avoid an obstacle into the ego path.",
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(50, 115),
        actor_kph=(30, 85),
        distance_m=(15, 65),
        actors=[_vehicle("evading", "swerve")],
        odd={"lane_count": [2, 3]},
        notes="Evasive action carried by the other vehicle; see module docstring.",
    ),
    34: _Spec(
        slug="non-collision-incident",
        family=ScenarioFamily.NON_COLLISION,
        description=(
            "A damaging or injury-producing event with no conflict partner "
            "(rollover, fire, occupant injury without impact)."
        ),
        roads=[RoadGeometry.STRAIGHT, RoadGeometry.CURVE],
        weathers=[Weather.CLEAR, Weather.RAIN],
        lightings=_DAY_NIGHT,
        ego_kph=(50, 110),
        actor_kph=(0, 0),
        distance_m=(20, 60),
        actors=[],
        odd={"surface": ["dry", "wet"]},
        simulable=False,
        notes=(
            "No conflict partner exists, so the kinematic layer cannot represent "
            "this scenario. Catalogued for typology completeness and excluded "
            "from concrete generation."
        ),
    ),
    35: _Spec(
        slug="object-crash-with-prior-maneuver",
        family=ScenarioFamily.OBJECT,
        description="The ego strikes an object in its path while mid-manoeuvre.",
        roads=_OPEN,
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(40, 100),
        actor_kph=(0, 0),
        distance_m=(15, 60),
        actors=[_obstacle("object", length=1.5, width=1.2, height=0.8)],
        odd={"object_type": ["debris", "cargo", "barrier"], "prior_action": ["turning"]},
    ),
    36: _Spec(
        slug="object-crash-without-prior-maneuver",
        family=ScenarioFamily.OBJECT,
        description="The ego travelling straight strikes an object in the roadway.",
        roads=[RoadGeometry.STRAIGHT, RoadGeometry.HIGHWAY, RoadGeometry.CURVE],
        weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
        lightings=_ALL_LIGHT,
        ego_kph=(50, 120),
        actor_kph=(0, 0),
        distance_m=(15, 70),
        actors=[_obstacle("object", length=1.5, width=1.2, height=0.8)],
        odd={"object_type": ["debris", "cargo", "barrier"]},
    ),
}


def _nhtsa_scenarios() -> list[LogicalScenario]:
    """Join the published facts with the modelling specs."""
    out: list[LogicalScenario] = []
    for number in sorted(_NHTSA_FACTS):
        name, group, crashes, share = _NHTSA_FACTS[number]
        spec = _NHTSA_SPECS[number]
        notes = " ".join(part for part in (spec.notes, _RANGE_NOTE) if part)
        out.append(
            LogicalScenario(
                id=f"nhtsa-{number:02d}-{spec.slug}",
                name=name,
                family=spec.family,
                description=spec.description,
                provenance=Provenance(
                    source=SourceType.NHTSA_PRECRASH,
                    citation=(
                        f"{_PRIMARY} pre-crash scenario {number} "
                        f"({name}); group '{group}' and 2011-2015 statistics {_STATS}"
                    ),
                    notes=notes,
                ),
                crash_frequency_weight=round(share / _MAX_SHARE_PCT, 4),
                nhtsa_scenario_number=number,
                annual_crashes=crashes,
                crash_share_pct=share,
                simulable=spec.simulable,
                road_geometries=spec.roads,
                weathers=spec.weathers,
                lightings=spec.lightings,
                ego_speed_kph=ParamRange(min=spec.ego_kph[0], max=spec.ego_kph[1], unit="kph"),
                actor_speed_kph=ParamRange(
                    min=spec.actor_kph[0], max=spec.actor_kph[1], unit="kph"
                ),
                distance_m=ParamRange(min=spec.distance_m[0], max=spec.distance_m[1], unit="m"),
                ttc_s=(
                    ParamRange(min=spec.ttc_s[0], max=spec.ttc_s[1], unit="s")
                    if spec.ttc_s
                    else None
                ),
                actors=spec.actors,
                odd_params=spec.odd,
            )
        )
    return out


def _regulatory_scenarios() -> list[LogicalScenario]:
    """UNECE R157 and Euro NCAP scenarios, with their exact regulatory parameters."""
    return [
        LogicalScenario(
            id="r157-cut-in",
            name="R157 cut-in",
            family=ScenarioFamily.CUT_IN,
            description=(
                "Other vehicle suddenly merges in front of ego. "
                "Risk perception 0.4s; lateral wander threshold 0.375m; THW max 2.0s."
            ),
            provenance=Provenance(
                source=SourceType.UNECE_R157,
                citation="UNECE R157 Annex 4 App.3 cut-in; risk_perception=0.4s; wander=0.375m",
            ),
            crash_frequency_weight=0.9,
            road_geometries=[RoadGeometry.HIGHWAY, RoadGeometry.STRAIGHT],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=40, max=130, unit="kph"),
            actor_speed_kph=ParamRange(min=30, max=120, unit="kph"),
            distance_m=ParamRange(min=5, max=40, unit="m"),
            ttc_s=ParamRange(min=0.6, max=3.0, unit="s"),
            actors=[ActorSpec(actor_type="vehicle", role="cut_in", behavior="cut_in")],
            r157_params={
                "risk_perception_s": 0.4,
                "reaction_s": 0.75,
                "lateral_wander_m": 0.375,
                "max_thw_s": 2.0,
            },
            odd_params={"relative_speed_kph": [-20, -10, 0, 10]},
        ),
        LogicalScenario(
            id="r157-cut-out",
            name="R157 cut-out revealing obstacle",
            family=ScenarioFamily.CUT_OUT,
            description=(
                "Lead vehicle exits lane revealing static obstacle. "
                "Wander threshold 0.375m; risk perception 0.4s."
            ),
            provenance=Provenance(
                source=SourceType.UNECE_R157,
                citation="UNECE R157 Annex 4 App.3 cut-out; wander=0.375m",
            ),
            crash_frequency_weight=0.7,
            road_geometries=[RoadGeometry.HIGHWAY, RoadGeometry.STRAIGHT],
            weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
            lightings=[Lighting.DAY, Lighting.DUSK],
            ego_speed_kph=ParamRange(min=40, max=120, unit="kph"),
            actor_speed_kph=ParamRange(min=40, max=120, unit="kph"),
            distance_m=ParamRange(min=10, max=50, unit="m"),
            actors=[
                ActorSpec(actor_type="vehicle", role="lead", behavior="cut_out"),
                ActorSpec(
                    actor_type="static", role="obstacle", length_m=4.5, width_m=1.8, height_m=1.5
                ),
            ],
            r157_params={"risk_perception_s": 0.4, "lateral_wander_m": 0.375, "max_thw_s": 2.0},
        ),
        LogicalScenario(
            id="r157-deceleration",
            name="R157 sudden lead deceleration",
            family=ScenarioFamily.DECELERATION,
            description=(
                "Lead vehicle decelerates above 5 m/s^2 threshold. "
                "Risk perception begins at that threshold."
            ),
            provenance=Provenance(
                source=SourceType.UNECE_R157,
                citation=(
                    "UNECE R157 Annex 4 App.3 deceleration; thresh=5m/s^2; risk_perception=0.4s"
                ),
            ),
            crash_frequency_weight=0.95,
            road_geometries=[RoadGeometry.HIGHWAY, RoadGeometry.STRAIGHT],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=40, max=130, unit="kph"),
            actor_speed_kph=ParamRange(min=40, max=130, unit="kph"),
            distance_m=ParamRange(min=8, max=50, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="lead", behavior="brake")],
            r157_params={
                "risk_perception_s": 0.4,
                "reaction_s": 0.75,
                "decel_threshold_mps2": 5.0,
            },
            odd_params={"lead_decel_mps2": [5, 6, 7, 8, 9]},
        ),
        LogicalScenario(
            id="euro-cpna-50",
            name="Euro NCAP CPNA-50 adult nearside",
            family=ScenarioFamily.VRU_CROSSING,
            description="Car-to-Pedestrian Nearside Adult, 50% impact point.",
            provenance=Provenance(
                source=SourceType.EURO_NCAP,
                citation="Euro NCAP AEB VRU v4.5.1 CPNA-50",
            ),
            crash_frequency_weight=0.5,
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.INTERSECTION],
            weathers=[Weather.CLEAR],
            lightings=[Lighting.DAY],
            ego_speed_kph=ParamRange(min=20, max=60, unit="kph"),
            actor_speed_kph=ParamRange(min=5, max=5, unit="kph"),
            distance_m=ParamRange(min=10, max=40, unit="m"),
            actors=[
                ActorSpec(
                    actor_type="pedestrian",
                    role="nearside",
                    length_m=0.5,
                    width_m=0.5,
                    height_m=1.8,
                    behavior="cross",
                )
            ],
            odd_params={"impact_offset_pct": [50], "approach": ["nearside"]},
        ),
        LogicalScenario(
            id="euro-cpfa-50",
            name="Euro NCAP CPFA-50 adult farside",
            family=ScenarioFamily.VRU_CROSSING,
            description="Car-to-Pedestrian Farside Adult, 50% impact point.",
            provenance=Provenance(
                source=SourceType.EURO_NCAP,
                citation="Euro NCAP AEB VRU v4.5.1 CPFA-50",
            ),
            crash_frequency_weight=0.45,
            road_geometries=[RoadGeometry.STRAIGHT],
            weathers=[Weather.CLEAR],
            lightings=[Lighting.DAY],
            ego_speed_kph=ParamRange(min=20, max=60, unit="kph"),
            actor_speed_kph=ParamRange(min=5, max=8, unit="kph"),
            distance_m=ParamRange(min=15, max=45, unit="m"),
            actors=[
                ActorSpec(
                    actor_type="pedestrian",
                    role="farside",
                    length_m=0.5,
                    width_m=0.5,
                    height_m=1.8,
                    behavior="cross",
                )
            ],
            odd_params={"impact_offset_pct": [50], "approach": ["farside"]},
        ),
        LogicalScenario(
            id="euro-cpta-50",
            name="Euro NCAP CPTA-50 turning adult",
            family=ScenarioFamily.VRU_CROSSING,
            description="Car-to-Pedestrian Turning Adult 50% at junction.",
            provenance=Provenance(
                source=SourceType.EURO_NCAP,
                citation="Euro NCAP AEB VRU v4.5.1 CPTA-50",
            ),
            crash_frequency_weight=0.4,
            road_geometries=[RoadGeometry.INTERSECTION],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.DUSK],
            ego_speed_kph=ParamRange(min=10, max=30, unit="kph"),
            actor_speed_kph=ParamRange(min=5, max=5, unit="kph"),
            distance_m=ParamRange(min=5, max=20, unit="m"),
            actors=[
                ActorSpec(
                    actor_type="pedestrian",
                    role="turning_path",
                    length_m=0.5,
                    width_m=0.5,
                    height_m=1.8,
                    behavior="cross",
                )
            ],
            odd_params={"impact_offset_pct": [25, 50, 75], "turn": ["left", "right"]},
        ),
    ]


def _hazop_scenarios() -> list[LogicalScenario]:
    """Sensor-degradation scenarios derived by applying HAZOP guide words to the ODD."""
    return [
        LogicalScenario(
            id="hazop-lidar-rain-dropout",
            name="Lidar rain dropout with lead vehicle",
            family=ScenarioFamily.SENSOR_DEGRADATION,
            description="Rear-end geometry under heavy rain lidar dropout (HAZOP: less sensing).",
            provenance=Provenance(
                source=SourceType.HAZOP,
                citation="HAZOP guideword=less on ODD.lidar_returns + rear-end geometry",
            ),
            crash_frequency_weight=0.3,
            road_geometries=[RoadGeometry.HIGHWAY, RoadGeometry.STRAIGHT],
            weathers=[Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=50, max=110, unit="kph"),
            actor_speed_kph=ParamRange(min=20, max=100, unit="kph"),
            distance_m=ParamRange(min=10, max=40, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="lead", behavior="brake")],
            odd_params={"lidar_dropout": [0.2, 0.4, 0.6], "rain_intensity": [0.5, 0.8, 1.0]},
        ),
        LogicalScenario(
            id="hazop-occluded-ped-dusk",
            name="Occluded pedestrian at dusk",
            family=ScenarioFamily.PEDESTRIAN,
            description="Pedestrian emerges from parked-car occlusion at dusk (HAZOP: other than).",
            provenance=Provenance(
                source=SourceType.HAZOP,
                citation="HAZOP guideword=other_than on ODD.visibility + pedestrian",
            ),
            crash_frequency_weight=0.35,
            road_geometries=[RoadGeometry.STRAIGHT],
            weathers=[Weather.CLEAR, Weather.FOG],
            lightings=[Lighting.DUSK, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=25, max=50, unit="kph"),
            actor_speed_kph=ParamRange(min=4, max=7, unit="kph"),
            distance_m=ParamRange(min=8, max=25, unit="m"),
            actors=[
                ActorSpec(actor_type="vehicle", role="parked", behavior="static"),
                ActorSpec(
                    actor_type="pedestrian",
                    role="emerging",
                    length_m=0.5,
                    width_m=0.5,
                    height_m=1.7,
                    behavior="cross",
                ),
            ],
            odd_params={"occlusion": ["full", "partial"]},
        ),
        LogicalScenario(
            id="hazop-camera-glare-cutin",
            name="Cut-in under camera glare",
            family=ScenarioFamily.CUT_IN,
            description="Cut-in with low-sun camera saturation (HAZOP: more on glare).",
            provenance=Provenance(
                source=SourceType.HAZOP,
                citation="HAZOP guideword=more on ODD.camera_glare + R157 cut-in",
            ),
            crash_frequency_weight=0.5,
            road_geometries=[RoadGeometry.HIGHWAY],
            weathers=[Weather.CLEAR],
            lightings=[Lighting.DUSK, Lighting.DAWN],
            ego_speed_kph=ParamRange(min=60, max=120, unit="kph"),
            actor_speed_kph=ParamRange(min=50, max=110, unit="kph"),
            distance_m=ParamRange(min=8, max=30, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="cut_in", behavior="cut_in")],
            odd_params={"camera_glare": [True], "dirt_occlusion": [0.0, 0.15, 0.3]},
        ),
        LogicalScenario(
            id="hazop-wrong-way-intersection",
            name="Wrong-way vehicle at intersection",
            family=ScenarioFamily.OPPOSITE_DIRECTION,
            description="Vehicle enters intersection from wrong direction (HAZOP: reverse).",
            provenance=Provenance(
                source=SourceType.HAZOP,
                citation="HAZOP guideword=reverse on ODD.traffic_direction",
            ),
            crash_frequency_weight=0.2,
            road_geometries=[RoadGeometry.INTERSECTION],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=30, max=60, unit="kph"),
            actor_speed_kph=ParamRange(min=30, max=70, unit="kph"),
            distance_m=ParamRange(min=15, max=50, unit="m"),
            actors=[
                ActorSpec(actor_type="vehicle", role="wrong_way", behavior="constant_velocity")
            ],
            odd_params={"signal_state": ["green", "yellow"]},
        ),
    ]


def build_catalog() -> list[LogicalScenario]:
    """The full logical scenario catalog.

    36 NHTSA pre-crash scenarios, 3 UNECE R157 scenarios, 3 Euro NCAP VRU
    protocols and 4 HAZOP-derived sensor-degradation scenarios.
    """
    return _nhtsa_scenarios() + _regulatory_scenarios() + _hazop_scenarios()


def catalog_by_id() -> dict[str, LogicalScenario]:
    return {s.id: s for s in build_catalog()}


def simulable_catalog() -> list[LogicalScenario]:
    """Catalog entries the kinematic layer can faithfully represent."""
    return [s for s in build_catalog() if s.simulable]
