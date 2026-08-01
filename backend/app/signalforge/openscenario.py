"""Export concrete scenarios as ASAM OpenSCENARIO (.xosc) bundles.

A scenario catalogue that cannot be executed is a spreadsheet.  This module
turns each :class:`~backend.app.signalforge.schema.ConcreteScenario` into an
OpenSCENARIO file plus the OpenDRIVE road it needs, so anyone with esmini,
CARLA, or any other OpenSCENARIO player can run it without installing
SignalForge.

Three design decisions are worth stating up front, because they are what make
the export useful rather than merely valid.

**The ego is a slot, not a driver.**  The ego is teleported in and given its
initial speed, and nothing else.  No scripted braking, no controller.  Whatever
system under test is being evaluated supplies the ego behaviour; the reference
driver's outcome travels alongside as metadata, not as scripted motion.  Setting
``reference_driver=True`` scripts the R157 competent-driver response instead,
which is what the fidelity check needs to reproduce SignalForge's own metrics.

**Challenger actors are reproducible, not reactive.**  Actors whose motion is
purely longitudinal (braking, constant speed, parked) map to native
``SpeedAction`` semantics, which are both readable and exact.  Everything with
lateral motion — cut-ins, crossing pedestrians, turning vehicles, encroaching
oncoming traffic — is exported as a ``FollowTrajectoryAction`` over the
simulated polyline with absolute timing.  That is deliberate: a benchmark needs
every system under test to face the *same* challenger motion, and it makes the
published criticality metrics reproducible in a third-party simulator rather
than dependent on that simulator's controllers.

**The frame is mirrored.**  SignalForge's kinematic layer places oncoming
traffic at negative y, which is a left-hand-traffic convention.  OpenDRIVE
right-hand traffic puts opposing lanes on the positive-t side, so the export
mirrors y (and heading).  Mirroring is a rigid transform: distances, times to
collision and every other criticality metric are preserved exactly.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.app.signalforge.opendrive import RoadLayout, plan_road, render_opendrive
from backend.app.signalforge.schema import ActorState, ConcreteScenario
from backend.app.signalforge.sim import simulate

OSC_REV_MAJOR = 1
OSC_REV_MINOR = 2

#: Behaviours whose motion a native OpenSCENARIO action reproduces exactly.
LONGITUDINAL_BEHAVIORS = frozenset({"constant_velocity", "brake", "static"})

#: R157 competent-driver parameters, used only in reference-driver mode.
R157_RISK_PERCEPTION_S = 0.4
R157_REACTION_S = 0.75
R157_BRAKE_MPS2 = 7.0


@dataclass(frozen=True)
class ExportBundle:
    """One exported scenario: the scenario file, its road, and how it was built."""

    scenario_id: str
    xosc: str
    xodr: str
    xodr_filename: str
    layout: RoadLayout
    #: Actor id -> the OpenSCENARIO construct used to drive it.
    actor_actions: dict[str, str]

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        """Write both files into ``out_dir`` and return their paths."""
        out_dir.mkdir(parents=True, exist_ok=True)
        xosc_path = out_dir / f"{self.scenario_id}.xosc"
        xodr_path = out_dir / self.xodr_filename
        xosc_path.write_text(self.xosc)
        xodr_path.write_text(self.xodr)
        return xosc_path, xodr_path


def _mirror_y(y: float) -> float:
    return -y


def _mirror_heading_rad(heading_deg: float) -> float:
    """Mirror a heading about the x axis and convert to radians."""
    return math.radians(-heading_deg)


def _safe_name(raw: str) -> str:
    """An XML-safe, OpenSCENARIO-friendly entity name."""
    cleaned = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in raw)
    return cleaned or "entity"


def _speed(vx: float, vy: float) -> float:
    return math.hypot(vx, vy)


def _crosses_road(actor: ActorState) -> bool:
    """True when an actor traverses the carriageway instead of driving along it.

    Crossing pedestrians, cyclists and animals start off the road and walk over
    it, so their lateral extent describes the scene, not the roadway.
    """
    if actor.behavior == "cross":
        return True
    return abs(actor.vy) > abs(actor.vx)


def _sim_trajectories(
    scenario: ConcreteScenario,
) -> tuple[list[float], dict[str, list[dict[str, float]]]]:
    """Run the kinematic sim and return timestamps plus per-actor world states."""
    result = simulate(scenario, record_frames=True, frame_stride=1)
    times: list[float] = []
    tracks: dict[str, list[dict[str, float]]] = {}
    for frame in result.frames:
        times.append(float(frame["t"]))
        for actor in frame["actors"]:
            tracks.setdefault(actor["id"], []).append(actor)
    return times, tracks


# ---------------------------------------------------------------------------
# Entity definitions
# ---------------------------------------------------------------------------


def _bounding_box(el: ET.Element, actor: ActorState) -> None:
    box = ET.SubElement(el, "BoundingBox")
    # Reference point sits at the rear axle for vehicles, so the box centre is
    # offset forward by roughly a third of the length.
    center_x = actor.length_m / 3.0 if actor.actor_type in ("vehicle", "cyclist") else 0.0
    ET.SubElement(
        box,
        "Center",
        x=f"{center_x:.3f}",
        y="0.0",
        z=f"{actor.height_m / 2.0:.3f}",
    )
    ET.SubElement(
        box,
        "Dimensions",
        width=f"{actor.width_m:.3f}",
        length=f"{actor.length_m:.3f}",
        height=f"{actor.height_m:.3f}",
    )


def _properties(el: ET.Element, props: dict[str, Any]) -> None:
    holder = ET.SubElement(el, "Properties")
    for key, value in props.items():
        ET.SubElement(holder, "Property", name=str(key), value=str(value))


def _axles(el: ET.Element, actor: ActorState) -> None:
    axles = ET.SubElement(el, "Axles")
    wheel = 0.7 if actor.actor_type == "vehicle" else 0.6
    track = max(0.6, actor.width_m - 0.2)
    ET.SubElement(
        axles,
        "FrontAxle",
        maxSteering="0.5236",
        wheelDiameter=f"{wheel}",
        trackWidth=f"{track:.3f}",
        positionX=f"{max(1.0, actor.length_m * 0.62):.3f}",
        positionZ=f"{wheel / 2:.3f}",
    )
    ET.SubElement(
        axles,
        "RearAxle",
        maxSteering="0.0",
        wheelDiameter=f"{wheel}",
        trackWidth=f"{track:.3f}",
        positionX="0.0",
        positionZ=f"{wheel / 2:.3f}",
    )


def _entity_element(actor: ActorState, *, model_id: int) -> ET.Element:
    """Build an inline entity definition — no catalogue reference, no 3D model.

    Bundles must run anywhere, so entities carry their own geometry.  ``model_id``
    is an esmini rendering hint that is harmless elsewhere.
    """
    obj = ET.Element("ScenarioObject", name=_safe_name(actor.id))

    if actor.actor_type == "pedestrian":
        el = ET.SubElement(
            obj,
            "Pedestrian",
            name=_safe_name(actor.id),
            mass="80",
            pedestrianCategory="pedestrian",
        )
        _bounding_box(el, actor)
        _properties(el, {"model_id": model_id})
    elif actor.actor_type == "animal":
        # OpenSCENARIO models animals as a pedestrian category rather than a
        # misc object, which keeps them as moving entities.
        el = ET.SubElement(
            obj,
            "Pedestrian",
            name=_safe_name(actor.id),
            mass="250",
            pedestrianCategory="animal",
        )
        _bounding_box(el, actor)
        _properties(el, {"model_id": model_id})
    elif actor.actor_type == "cyclist":
        el = ET.SubElement(
            obj, "Vehicle", name=_safe_name(actor.id), vehicleCategory="bicycle"
        )
        _bounding_box(el, actor)
        ET.SubElement(
            el, "Performance", maxSpeed="15", maxDeceleration="6", maxAcceleration="3"
        )
        _axles(el, actor)
        _properties(el, {"model_id": model_id})
    elif actor.actor_type == "static":
        el = ET.SubElement(
            obj,
            "MiscObject",
            name=_safe_name(actor.id),
            mass="500",
            miscObjectCategory="obstacle",
        )
        _bounding_box(el, actor)
        _properties(el, {"model_id": model_id})
    else:
        el = ET.SubElement(
            obj, "Vehicle", name=_safe_name(actor.id), vehicleCategory="car"
        )
        _bounding_box(el, actor)
        ET.SubElement(
            el, "Performance", maxSpeed="70", maxDeceleration="10", maxAcceleration="5"
        )
        _axles(el, actor)
        _properties(el, {"model_id": model_id})

    return obj


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _teleport(private: ET.Element, x: float, y: float, heading_deg: float) -> None:
    action = ET.SubElement(private, "PrivateAction")
    teleport = ET.SubElement(action, "TeleportAction")
    position = ET.SubElement(teleport, "Position")
    ET.SubElement(
        position,
        "WorldPosition",
        x=f"{x:.4f}",
        y=f"{_mirror_y(y):.4f}",
        z="0",
        h=f"{_mirror_heading_rad(heading_deg):.6f}",
    )


def _init_speed(private: ET.Element, speed: float) -> None:
    action = ET.SubElement(private, "PrivateAction")
    longitudinal = ET.SubElement(action, "LongitudinalAction")
    speed_action = ET.SubElement(longitudinal, "SpeedAction")
    ET.SubElement(
        speed_action,
        "SpeedActionDynamics",
        dynamicsShape="step",
        value="0.0",
        dynamicsDimension="time",
    )
    target = ET.SubElement(speed_action, "SpeedActionTarget")
    ET.SubElement(target, "AbsoluteTargetSpeed", value=f"{speed:.4f}")


def _sim_time_trigger(parent: ET.Element, name: str, at: float) -> None:
    """Start an event at simulation time ``at``.

    ``greaterOrEqual`` rather than ``greaterThan`` on purpose: the kinematic
    simulator acts on the first step where ``t >= trigger_t``, and
    ``greaterThan`` fires a whole timestep later, which showed up as a
    reproducible position offset in the fidelity check.
    """
    trigger = ET.SubElement(parent, "StartTrigger")
    group = ET.SubElement(trigger, "ConditionGroup")
    condition = ET.SubElement(group, "Condition", name=name, delay="0", conditionEdge="none")
    by_value = ET.SubElement(condition, "ByValueCondition")
    ET.SubElement(
        by_value,
        "SimulationTimeCondition",
        value=f"{max(0.0, at):.4f}",
        rule="greaterOrEqual",
    )


def _speed_change_action(
    parent: ET.Element, name: str, *, rate: float, target_speed: float
) -> None:
    action = ET.SubElement(parent, "Action", name=name)
    private = ET.SubElement(action, "PrivateAction")
    longitudinal = ET.SubElement(private, "LongitudinalAction")
    speed_action = ET.SubElement(longitudinal, "SpeedAction")
    ET.SubElement(
        speed_action,
        "SpeedActionDynamics",
        dynamicsShape="linear",
        value=f"{abs(rate):.4f}",
        dynamicsDimension="rate",
    )
    target = ET.SubElement(speed_action, "SpeedActionTarget")
    ET.SubElement(target, "AbsoluteTargetSpeed", value=f"{max(0.0, target_speed):.4f}")


def _follow_trajectory_action(
    parent: ET.Element,
    name: str,
    *,
    track: list[dict[str, float]],
    times: list[float],
    stride: int,
) -> None:
    action = ET.SubElement(parent, "Action", name=name)
    private = ET.SubElement(action, "PrivateAction")
    routing = ET.SubElement(private, "RoutingAction")
    follow = ET.SubElement(routing, "FollowTrajectoryAction")
    trajectory = ET.SubElement(follow, "Trajectory", closed="false", name=f"{name}_path")
    ET.SubElement(trajectory, "ParameterDeclarations")
    shape = ET.SubElement(trajectory, "Shape")
    polyline = ET.SubElement(shape, "Polyline")

    indices = list(range(0, len(track), max(1, stride)))
    if indices and indices[-1] != len(track) - 1:
        indices.append(len(track) - 1)

    for i in indices:
        state = track[i]
        vertex = ET.SubElement(polyline, "Vertex", time=f"{times[i]:.4f}")
        position = ET.SubElement(vertex, "Position")
        ET.SubElement(
            position,
            "WorldPosition",
            x=f"{state['x']:.4f}",
            y=f"{_mirror_y(state['y']):.4f}",
            z="0",
            h=f"{_mirror_heading_rad(state['heading_deg']):.6f}",
        )

    time_ref = ET.SubElement(follow, "TimeReference")
    ET.SubElement(time_ref, "Timing", domainAbsoluteRelative="absolute", scale="1", offset="0")
    ET.SubElement(follow, "TrajectoryFollowingMode", followingMode="position")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _provenance_parameters(scenario: ConcreteScenario) -> dict[str, str]:
    """Provenance and reference metrics, carried as scenario parameters.

    ``ParameterDeclarations`` is the one place OpenSCENARIO lets arbitrary
    key/value metadata ride along inside a schema-valid document, so the
    regulation clause or incident report behind a scenario survives the export
    instead of being stranded in the database.
    """
    provenance = scenario.provenance
    params: dict[str, str] = {
        "sf_scenario_id": scenario.id,
        "sf_logical_id": scenario.logical_id,
        "sf_family": scenario.family.value,
        "sf_provenance_source": provenance.source.value,
        "sf_provenance_citation": provenance.citation,
        "sf_provenance_parent": provenance.parent_id or "",
        "sf_seed": str(provenance.seed),
        "sf_weather": scenario.weather.value,
        "sf_lighting": scenario.lighting.value,
        "sf_road_geometry": scenario.road_geometry.value,
        "sf_crash_frequency_weight": f"{scenario.crash_frequency_weight:.4f}",
    }
    if provenance.notes:
        params["sf_provenance_notes"] = provenance.notes
    if scenario.difficulty is not None:
        params["sf_difficulty"] = scenario.difficulty.value
    metrics = scenario.metrics
    if metrics is not None:
        if metrics.min_ttc_s is not None:
            params["sf_reference_min_ttc_s"] = f"{metrics.min_ttc_s:.4f}"
        if metrics.min_distance_m is not None:
            params["sf_reference_min_distance_m"] = f"{metrics.min_distance_m:.4f}"
        if metrics.required_decel_mps2 is not None:
            params["sf_reference_required_decel_mps2"] = f"{metrics.required_decel_mps2:.4f}"
        if metrics.preventable is not None:
            params["sf_reference_preventable"] = str(metrics.preventable).lower()
        params["sf_reference_collision"] = str(metrics.collision).lower()
    return params


def _actor_maneuver(
    story_act: ET.Element,
    actor: ActorState,
    *,
    track: list[dict[str, float]],
    times: list[float],
    odd: dict[str, Any],
    stride: int,
    trajectory_mode: bool,
) -> str | None:
    """Add the maneuver driving one actor.  Returns the construct used, if any."""
    name = _safe_name(actor.id)
    behavior = actor.behavior

    if behavior == "static":
        return None
    if behavior == "constant_velocity" and not trajectory_mode:
        # Fully described by the init speed; nothing further to script.
        return None

    group = ET.SubElement(
        story_act, "ManeuverGroup", maximumExecutionCount="1", name=f"{name}_group"
    )
    actors_el = ET.SubElement(group, "Actors", selectTriggeringEntities="false")
    ET.SubElement(actors_el, "EntityRef", entityRef=name)
    maneuver = ET.SubElement(group, "Maneuver", name=f"{name}_{behavior}")
    event = ET.SubElement(
        maneuver,
        "Event",
        maximumExecutionCount="1",
        name=f"{name}_{behavior}_event",
        priority="overwrite",
    )

    if behavior == "brake" and not trajectory_mode:
        decel = float(odd.get("lead_decel_mps2", 6.0))
        _speed_change_action(
            event, f"{name}_brake_action", rate=decel, target_speed=0.0
        )
        _sim_time_trigger(event, f"{name}_brake_trigger", actor.trigger_t or 0.0)
        return "SpeedAction(linear,rate)"

    _follow_trajectory_action(
        event, f"{name}_trajectory", track=track, times=times, stride=stride
    )
    _sim_time_trigger(event, f"{name}_trajectory_trigger", 0.0)
    return "FollowTrajectoryAction(polyline)"


def _reference_driver_maneuver(story_act: ET.Element, scenario: ConcreteScenario) -> None:
    """Script the R157 competent-driver braking response for the ego.

    Only used to check that a third-party simulator reproduces SignalForge's own
    numbers.  A benchmark run leaves the ego unscripted.
    """
    delay = float(scenario.odd.get("risk_perception_s", R157_RISK_PERCEPTION_S)) + float(
        scenario.odd.get("reaction_s", R157_REACTION_S)
    )
    group = ET.SubElement(
        story_act, "ManeuverGroup", maximumExecutionCount="1", name="ego_reference_group"
    )
    actors_el = ET.SubElement(group, "Actors", selectTriggeringEntities="false")
    ET.SubElement(actors_el, "EntityRef", entityRef="Ego")
    maneuver = ET.SubElement(group, "Maneuver", name="ego_reference_driver")
    event = ET.SubElement(
        maneuver,
        "Event",
        maximumExecutionCount="1",
        name="ego_reference_brake",
        priority="overwrite",
    )
    _speed_change_action(
        event, "ego_reference_brake_action", rate=R157_BRAKE_MPS2, target_speed=0.0
    )
    _sim_time_trigger(event, "ego_reference_brake_trigger", delay)


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Pretty-print in place; ElementTree.indent is 3.9+, this keeps it explicit."""
    pad = "\n" + "  " * level
    if len(elem):
        if not (elem.text or "").strip():
            elem.text = pad + "  "
        for child in elem:
            _indent(child, level + 1)
        if not (elem.tail or "").strip():
            elem.tail = pad
        if not (elem[-1].tail or "").strip():
            elem[-1].tail = pad
    elif level and not (elem.tail or "").strip():
        elem.tail = pad


def export_scenario(
    scenario: ConcreteScenario,
    *,
    reference_driver: bool = False,
    trajectory_stride: int = 1,
    trajectory_mode: bool = False,
    author: str = "SignalForge",
) -> ExportBundle:
    """Convert one concrete scenario into an OpenSCENARIO bundle.

    ``trajectory_mode`` drives *every* actor from its simulated polyline instead
    of using native speed actions where they fit.  The default is more readable
    and re-parameterisable — a brake really is a ``SpeedAction`` — but it leaves
    the integration scheme up to the player, which costs about two metres over an
    eight-second braking manoeuvre.  Trajectory mode reproduces the simulated
    motion to within millimetres, which is what a reproducibility check wants.
    """
    times, tracks = _sim_trajectories(scenario)
    if not times:
        times = [0.0]

    # Road extent, in the exported (mirrored) frame.
    xs: list[float] = [scenario.ego.x]
    forward_ys: list[float] = [_mirror_y(scenario.ego.y)]
    oncoming_ys: list[float] = []

    ego_speed = _speed(scenario.ego.vx, scenario.ego.vy)
    # The ego is unscripted, so bound the road by how far it could travel.
    xs.append(scenario.ego.x + ego_speed * scenario.duration_s)

    for actor in scenario.actors:
        track = tracks.get(actor.id, []) or [
            {"x": actor.x, "y": actor.y, "heading_deg": actor.heading_deg}
        ]
        for state in track:
            xs.append(state["x"])

        # Only entities travelling *along* the road decide how wide it is.  A
        # pedestrian walking across from the verge would otherwise turn a
        # two-lane road into a fourteen-lane one.
        if _crosses_road(actor):
            continue
        opposing = actor.vx < -0.1
        for state in track:
            (oncoming_ys if opposing else forward_ys).append(_mirror_y(state["y"]))

    layout = plan_road(xs, forward_ys, oncoming_ys)
    xodr_filename = f"{scenario.id}.xodr"

    root = ET.Element("OpenSCENARIO")
    ET.SubElement(
        root,
        "FileHeader",
        revMajor=str(OSC_REV_MAJOR),
        revMinor=str(OSC_REV_MINOR),
        date="1970-01-01T00:00:00",
        description=f"{scenario.name} | {scenario.provenance.citation}",
        author=author,
    )

    params = _provenance_parameters(scenario)
    param_decls = ET.SubElement(root, "ParameterDeclarations")
    for key, value in params.items():
        ET.SubElement(
            param_decls, "ParameterDeclaration", name=key, parameterType="string", value=value
        )

    ET.SubElement(root, "CatalogLocations")
    road_network = ET.SubElement(root, "RoadNetwork")
    ET.SubElement(road_network, "LogicFile", filepath=xodr_filename)

    entities = ET.SubElement(root, "Entities")
    ego_object = _entity_element(scenario.ego, model_id=0)
    ego_object.set("name", "Ego")
    entities.append(ego_object)
    for i, actor in enumerate(scenario.actors, start=1):
        entities.append(_entity_element(actor, model_id=i))

    storyboard = ET.SubElement(root, "Storyboard")
    init = ET.SubElement(storyboard, "Init")
    init_actions = ET.SubElement(init, "Actions")

    ego_private = ET.SubElement(init_actions, "Private", entityRef="Ego")
    _teleport(ego_private, scenario.ego.x, scenario.ego.y, scenario.ego.heading_deg)
    _init_speed(ego_private, ego_speed)

    for actor in scenario.actors:
        private = ET.SubElement(init_actions, "Private", entityRef=_safe_name(actor.id))
        _teleport(private, actor.x, actor.y, actor.heading_deg)
        speed = _speed(actor.vx, actor.vy)
        if actor.behavior != "static" or speed > 0:
            _init_speed(private, speed)

    story = ET.SubElement(storyboard, "Story", name="SignalForgeStory")
    act = ET.SubElement(story, "Act", name="SignalForgeAct")

    actor_actions: dict[str, str] = {}
    for actor in scenario.actors:
        used = _actor_maneuver(
            act,
            actor,
            track=tracks.get(actor.id, []),
            times=times,
            odd=scenario.odd,
            stride=trajectory_stride,
            trajectory_mode=trajectory_mode,
        )
        actor_actions[actor.id] = used or "Init only"

    if reference_driver:
        _reference_driver_maneuver(act, scenario)
        actor_actions["ego"] = "SpeedAction(R157 competent driver)"
    else:
        actor_actions["ego"] = "Init only (system under test)"

    _sim_time_trigger(act, "act_start", 0.0)

    stop = ET.SubElement(storyboard, "StopTrigger")
    stop_group = ET.SubElement(stop, "ConditionGroup")
    stop_condition = ET.SubElement(
        stop_group, "Condition", name="scenario_end", delay="0", conditionEdge="none"
    )
    stop_by_value = ET.SubElement(stop_condition, "ByValueCondition")
    ET.SubElement(
        stop_by_value,
        "SimulationTimeCondition",
        value=f"{scenario.duration_s:.4f}",
        rule="greaterThan",
    )

    _indent(root)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )

    return ExportBundle(
        scenario_id=scenario.id,
        xosc=xml,
        xodr=render_opendrive(layout, name=scenario.id),
        xodr_filename=xodr_filename,
        layout=layout,
        actor_actions=actor_actions,
    )


def export_many(
    scenarios: Iterable[ConcreteScenario],
    out_dir: Path,
    **kwargs: Any,
) -> list[Path]:
    """Export a batch of scenarios into ``out_dir``, returning the .xosc paths."""
    written: list[Path] = []
    for scenario in scenarios:
        bundle = export_scenario(scenario, **kwargs)
        xosc_path, _ = bundle.write(out_dir)
        written.append(xosc_path)
    return written
