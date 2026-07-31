"""Hand-encoded logical scenarios from NHTSA, UNECE R157, and Euro NCAP."""

from __future__ import annotations

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

# Approximate relative weights from NHTSA 2011-2015 pre-crash typology
# (normalized within groups; absolute magnitudes illustrative of ranking).
_NHTSA_WEIGHTS = {
    ScenarioFamily.REAR_END: 1.00,
    ScenarioFamily.CROSSING_PATHS: 0.72,
    ScenarioFamily.ROAD_DEPARTURE: 0.55,
    ScenarioFamily.LANE_CHANGE: 0.38,
    ScenarioFamily.CONTROL_LOSS: 0.32,
    ScenarioFamily.PEDESTRIAN: 0.28,
    ScenarioFamily.PEDALCYCLIST: 0.18,
    ScenarioFamily.OPPOSITE_DIRECTION: 0.22,
    ScenarioFamily.ANIMAL: 0.15,
}


def build_catalog() -> list[LogicalScenario]:
    scenarios: list[LogicalScenario] = []

    # --- NHTSA nine groups ---
    scenarios.append(
        LogicalScenario(
            id="nhtsa-rear-end-lead-decel",
            name="Rear-end: lead vehicle decelerates",
            family=ScenarioFamily.REAR_END,
            description="Ego follows lead vehicle that suddenly brakes.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / rear-end group",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.REAR_END],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.HIGHWAY],
            weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
            lightings=[Lighting.DAY, Lighting.DUSK, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=40, max=110, unit="kph"),
            actor_speed_kph=ParamRange(min=0, max=100, unit="kph"),
            distance_m=ParamRange(min=8, max=60, unit="m"),
            ttc_s=ParamRange(min=0.8, max=4.0, unit="s"),
            actors=[ActorSpec(actor_type="vehicle", role="lead", behavior="brake")],
            odd_params={"occlusion": ["none", "partial"], "lead_decel_mps2": [3, 5, 7, 9]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-crossing-paths-ltap",
            name="Crossing paths: left turn across path",
            family=ScenarioFamily.CROSSING_PATHS,
            description="Oncoming vehicle turns left across ego path at intersection.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / crossing paths",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.CROSSING_PATHS],
            road_geometries=[RoadGeometry.INTERSECTION],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.NIGHT, Lighting.DUSK],
            ego_speed_kph=ParamRange(min=30, max=70, unit="kph"),
            actor_speed_kph=ParamRange(min=15, max=50, unit="kph"),
            distance_m=ParamRange(min=10, max=40, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="crossing", behavior="left_turn")],
            odd_params={"signal_state": ["green", "yellow", "red"]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-road-departure-edge",
            name="Road edge departure without prior maneuver",
            family=ScenarioFamily.ROAD_DEPARTURE,
            description="Ego drifts toward road edge / soft shoulder.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / road departure",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.ROAD_DEPARTURE],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.CURVE, RoadGeometry.HIGHWAY],
            weathers=[Weather.CLEAR, Weather.RAIN, Weather.SNOW],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=50, max=120, unit="kph"),
            actor_speed_kph=ParamRange(min=0, max=0, unit="kph"),
            distance_m=ParamRange(min=1, max=5, unit="m"),
            actors=[ActorSpec(actor_type="static", role="barrier", length_m=20, width_m=0.5, height_m=1.0)],
            odd_params={"surface": ["dry", "wet", "ice"]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-lane-change-same-dir",
            name="Lane change conflict same direction",
            family=ScenarioFamily.LANE_CHANGE,
            description="Adjacent vehicle changes into ego lane with short gap.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / lane change",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.LANE_CHANGE],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.HIGHWAY],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.DUSK, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=50, max=120, unit="kph"),
            actor_speed_kph=ParamRange(min=40, max=110, unit="kph"),
            distance_m=ParamRange(min=5, max=30, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="adjacent", behavior="cut_in")],
            odd_params={"lane_count": [2, 3, 4]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-control-loss-skid",
            name="Control loss without prior action",
            family=ScenarioFamily.CONTROL_LOSS,
            description="Other vehicle loses control and enters ego path.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / control loss",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.CONTROL_LOSS],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.CURVE],
            weathers=[Weather.RAIN, Weather.SNOW, Weather.CLEAR],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=40, max=100, unit="kph"),
            actor_speed_kph=ParamRange(min=30, max=90, unit="kph"),
            distance_m=ParamRange(min=10, max=50, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="unstable", behavior="swerve")],
            odd_params={"surface": ["wet", "ice", "dry"]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-pedestrian-crossing",
            name="Pedestrian crossing roadway",
            family=ScenarioFamily.PEDESTRIAN,
            description="Pedestrian enters roadway, possibly from occlusion.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / pedestrian",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.PEDESTRIAN],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.INTERSECTION],
            weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
            lightings=[Lighting.DAY, Lighting.DUSK, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=20, max=60, unit="kph"),
            actor_speed_kph=ParamRange(min=3, max=8, unit="kph"),
            distance_m=ParamRange(min=8, max=35, unit="m"),
            actors=[
                ActorSpec(
                    actor_type="pedestrian",
                    role="crossing",
                    length_m=0.6,
                    width_m=0.6,
                    height_m=1.7,
                    behavior="cross",
                )
            ],
            odd_params={"occlusion": ["none", "partial", "full"], "jaywalk": [True, False]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-pedalcyclist-crossing",
            name="Cyclist crossing or parallel",
            family=ScenarioFamily.PEDALCYCLIST,
            description="Cyclist crosses or rides parallel into conflict.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / pedalcyclist",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.PEDALCYCLIST],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.INTERSECTION],
            weathers=[Weather.CLEAR, Weather.RAIN],
            lightings=[Lighting.DAY, Lighting.DUSK],
            ego_speed_kph=ParamRange(min=25, max=60, unit="kph"),
            actor_speed_kph=ParamRange(min=10, max=30, unit="kph"),
            distance_m=ParamRange(min=10, max=40, unit="m"),
            actors=[
                ActorSpec(
                    actor_type="cyclist",
                    role="crossing",
                    length_m=1.8,
                    width_m=0.6,
                    height_m=1.7,
                    behavior="cross",
                )
            ],
            odd_params={"occlusion": ["none", "partial"]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-opposite-direction",
            name="Opposite direction encroachment",
            family=ScenarioFamily.OPPOSITE_DIRECTION,
            description="Oncoming vehicle encroaches into ego lane.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / opposite direction",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.OPPOSITE_DIRECTION],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.CURVE],
            weathers=[Weather.CLEAR, Weather.RAIN, Weather.FOG],
            lightings=[Lighting.DAY, Lighting.NIGHT],
            ego_speed_kph=ParamRange(min=40, max=100, unit="kph"),
            actor_speed_kph=ParamRange(min=40, max=100, unit="kph"),
            distance_m=ParamRange(min=30, max=120, unit="m"),
            actors=[ActorSpec(actor_type="vehicle", role="oncoming", behavior="encroach")],
            odd_params={"encroach_m": [0.5, 1.0, 1.5, 2.0]},
        )
    )
    scenarios.append(
        LogicalScenario(
            id="nhtsa-animal-crossing",
            name="Animal in roadway",
            family=ScenarioFamily.ANIMAL,
            description="Large animal enters roadway ahead of ego.",
            provenance=Provenance(
                source=SourceType.NHTSA_PRECRASH,
                citation="NHTSA DOT HS 812 834 / animal",
            ),
            crash_frequency_weight=_NHTSA_WEIGHTS[ScenarioFamily.ANIMAL],
            road_geometries=[RoadGeometry.STRAIGHT, RoadGeometry.HIGHWAY, RoadGeometry.CURVE],
            weathers=[Weather.CLEAR, Weather.FOG],
            lightings=[Lighting.NIGHT, Lighting.DAWN, Lighting.DUSK],
            ego_speed_kph=ParamRange(min=50, max=110, unit="kph"),
            actor_speed_kph=ParamRange(min=5, max=40, unit="kph"),
            distance_m=ParamRange(min=15, max=60, unit="m"),
            actors=[
                ActorSpec(
                    actor_type="animal",
                    role="crossing",
                    length_m=2.0,
                    width_m=0.8,
                    height_m=1.4,
                    behavior="cross",
                )
            ],
            odd_params={"animal_size": ["deer", "dog", "livestock"]},
        )
    )

    # --- UNECE R157 ---
    scenarios.append(
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
        )
    )
    scenarios.append(
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
                ActorSpec(actor_type="static", role="obstacle", length_m=4.5, width_m=1.8, height_m=1.5),
            ],
            r157_params={"risk_perception_s": 0.4, "lateral_wander_m": 0.375, "max_thw_s": 2.0},
        )
    )
    scenarios.append(
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
                citation="UNECE R157 Annex 4 App.3 deceleration; thresh=5m/s^2; risk_perception=0.4s",
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
        )
    )

    # --- Euro NCAP VRU ---
    scenarios.append(
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
        )
    )
    scenarios.append(
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
        )
    )
    scenarios.append(
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
        )
    )

    # --- HAZOP / sensor degradation ---
    scenarios.append(
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
        )
    )
    scenarios.append(
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
        )
    )
    scenarios.append(
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
        )
    )
    scenarios.append(
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
            actors=[ActorSpec(actor_type="vehicle", role="wrong_way", behavior="constant_velocity")],
            odd_params={"signal_state": ["green", "yellow"]},
        )
    )

    return scenarios


def catalog_by_id() -> dict[str, LogicalScenario]:
    return {s.id: s for s in build_catalog()}
