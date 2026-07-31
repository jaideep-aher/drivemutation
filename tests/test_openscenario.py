"""Tests for the OpenSCENARIO / OpenDRIVE export.

Tests that need esmini are skipped when it is not installed, so the suite still
runs on a bare checkout.  CI installs esmini so they do run there — see
``.github/workflows/ci.yml``.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from backend.app.signalforge.catalog import build_catalog
from backend.app.signalforge.esmini import (
    TRAJECTORY_POSITION_TOLERANCE_M,
    check_fidelity,
    find_esmini,
    run_esmini,
)
from backend.app.signalforge.expand import expand_logical
from backend.app.signalforge.opendrive import LANE_WIDTH, plan_road, render_opendrive
from backend.app.signalforge.openscenario import export_scenario
from backend.app.signalforge.sim import annotate_scenario

needs_esmini = pytest.mark.skipif(
    find_esmini() is None, reason="esmini not installed (set ESMINI or add to PATH)"
)


def sample_scenarios():
    """One concrete scenario per logical scenario, covering every family."""
    out = []
    for logical in build_catalog():
        batch = expand_logical(logical, samples_per_combo=1, seed=5, max_per_logical=1)
        if batch:
            out.append(annotate_scenario(batch[0]))
    return out


def scenario_ids(scenarios):
    return [s.id for s in scenarios]


SCENARIOS = sample_scenarios()


# ---------------------------------------------------------------------------
# Road generation
# ---------------------------------------------------------------------------


def test_lane_geometry_round_trips():
    layout = plan_road(xs=[0.0, 200.0], forward_ys=[0.0, -3.5, 3.5], oncoming_ys=[])
    # The ego lane centre must land exactly on y = 0, which is what lets the
    # Cartesian sim frame be used as world coordinates.
    assert layout.lane_center_y(layout.ego_lane_id) == pytest.approx(0.0)
    for lane_id in range(-layout.n_forward, 0):
        y = layout.lane_center_y(lane_id)
        assert layout.lane_id_at(y) == lane_id


def test_oncoming_traffic_gets_opposing_lanes():
    layout = plan_road(xs=[0.0, 200.0], forward_ys=[0.0], oncoming_ys=[3.5])
    assert layout.n_oncoming >= 1
    # Opposing lanes sit above the reference line; forward lanes below it.
    assert layout.lane_center_y(1) > layout.y_ref
    assert layout.lane_center_y(layout.ego_lane_id) < layout.y_ref


def test_road_is_long_enough_for_the_scenario():
    layout = plan_road(xs=[0.0, 300.0], forward_ys=[0.0], oncoming_ys=[])
    assert layout.length >= 300.0
    assert layout.x_start <= 0.0


def test_crossing_actors_do_not_widen_the_road():
    """A pedestrian walking across is not a reason to build a fourteen-lane road."""
    scenario = next(s for s in SCENARIOS if s.family.value in ("pedestrian", "vru_crossing"))
    bundle = export_scenario(scenario)
    assert bundle.layout.n_forward <= 3


def test_opendrive_is_well_formed():
    layout = plan_road(xs=[0.0, 200.0], forward_ys=[0.0, -3.5], oncoming_ys=[3.5])
    root = ET.fromstring(render_opendrive(layout))
    assert root.tag == "OpenDRIVE"
    road = root.find("road")
    assert road is not None
    lanes = road.findall(".//lane")
    driving = [el for el in lanes if el.get("type") == "driving"]
    assert len(driving) == layout.n_forward + layout.n_oncoming
    for lane in driving:
        width = lane.find("width")
        assert width is not None and float(width.get("a")) == LANE_WIDTH


# ---------------------------------------------------------------------------
# Scenario generation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=scenario_ids(SCENARIOS))
def test_export_is_well_formed_xml(scenario):
    bundle = export_scenario(scenario)
    root = ET.fromstring(bundle.xosc)
    assert root.tag == "OpenSCENARIO"

    header = root.find("FileHeader")
    assert header is not None
    assert header.get("revMajor") == "1"

    # Every actor plus the ego must exist as an entity, exactly once.
    names = [el.get("name") for el in root.findall("./Entities/ScenarioObject")]
    assert "Ego" in names
    assert len(names) == len(set(names)), "entity names must be unique"
    assert len(names) == len(scenario.actors) + 1

    ET.fromstring(bundle.xodr)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=scenario_ids(SCENARIOS))
def test_bundle_is_self_contained(scenario):
    """No catalogue references, no scene graph, no path outside the bundle."""
    bundle = export_scenario(scenario)
    root = ET.fromstring(bundle.xosc)

    assert root.find(".//CatalogReference") is None, "catalogue reference breaks portability"
    assert root.find(".//SceneGraphFile") is None, "scene graph file breaks portability"

    logic = root.find("./RoadNetwork/LogicFile")
    assert logic is not None
    filepath = logic.get("filepath")
    assert filepath == bundle.xodr_filename
    assert "/" not in filepath and ".." not in filepath, "road must sit beside the scenario"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=scenario_ids(SCENARIOS))
def test_entities_carry_their_own_geometry(scenario):
    bundle = export_scenario(scenario)
    root = ET.fromstring(bundle.xosc)
    for obj in root.findall("./Entities/ScenarioObject"):
        box = obj.find(".//BoundingBox/Dimensions")
        assert box is not None, f"{obj.get('name')} has no bounding box"
        assert float(box.get("length")) > 0
        assert float(box.get("width")) > 0
        assert float(box.get("height")) > 0


def test_provenance_survives_the_export():
    scenario = SCENARIOS[0]
    bundle = export_scenario(scenario)
    root = ET.fromstring(bundle.xosc)
    params = {
        el.get("name"): el.get("value")
        for el in root.findall("./ParameterDeclarations/ParameterDeclaration")
    }
    assert params["sf_scenario_id"] == scenario.id
    assert params["sf_logical_id"] == scenario.logical_id
    assert params["sf_provenance_citation"] == scenario.provenance.citation
    assert params["sf_provenance_source"] == scenario.provenance.source.value
    # The citation also rides in the header description, where a human sees it.
    assert scenario.provenance.citation in root.find("FileHeader").get("description")


def test_ego_is_unscripted_by_default():
    """The ego is the slot for the system under test, not a scripted driver."""
    scenario = next(s for s in SCENARIOS if s.family.value == "rear_end")
    root = ET.fromstring(export_scenario(scenario).xosc)
    ego_groups = [
        group
        for group in root.findall(".//ManeuverGroup")
        if any(
            ref.get("entityRef") == "Ego" for ref in group.findall("./Actors/EntityRef")
        )
    ]
    assert ego_groups == []

    # Opting in gives the ego the R157 competent-driver response.
    root = ET.fromstring(export_scenario(scenario, reference_driver=True).xosc)
    ego_groups = [
        group
        for group in root.findall(".//ManeuverGroup")
        if any(
            ref.get("entityRef") == "Ego" for ref in group.findall("./Actors/EntityRef")
        )
    ]
    assert len(ego_groups) == 1


def test_braking_maps_to_a_native_speed_action():
    scenario = next(
        s for s in SCENARIOS if any(a.behavior == "brake" for a in s.actors)
    )
    root = ET.fromstring(export_scenario(scenario).xosc)
    dynamics = root.find(".//ManeuverGroup//SpeedActionDynamics")
    assert dynamics is not None
    assert dynamics.get("dynamicsShape") == "linear"
    assert dynamics.get("dynamicsDimension") == "rate"
    expected = float(scenario.odd.get("lead_decel_mps2", 6.0))
    assert float(dynamics.get("value")) == pytest.approx(expected)


def test_trajectory_mode_scripts_every_moving_actor():
    scenario = next(
        s for s in SCENARIOS if any(a.behavior == "brake" for a in s.actors)
    )
    root = ET.fromstring(export_scenario(scenario, trajectory_mode=True).xosc)
    assert root.find(".//FollowTrajectoryAction") is not None
    # Braking is replayed rather than re-integrated by the player.
    assert root.find(".//ManeuverGroup//SpeedActionDynamics") is None


def test_triggers_fire_on_the_same_step_as_the_simulator():
    """greaterThan would fire a timestep late and shift every braking actor."""
    scenario = next(s for s in SCENARIOS if any(a.behavior == "brake" for a in s.actors))
    root = ET.fromstring(export_scenario(scenario).xosc)
    conditions = root.findall(".//SimulationTimeCondition")
    assert conditions
    starts = [
        el
        for el in conditions
        if el.get("rule") == "greaterOrEqual"
    ]
    assert starts, "start triggers must use greaterOrEqual"


def test_mirroring_preserves_relative_geometry():
    """Mirroring y is a rigid transform, so distances must be untouched."""
    scenario = next(s for s in SCENARIOS if s.actors)
    root = ET.fromstring(export_scenario(scenario).xosc)
    positions = {}
    for private in root.findall("./Storyboard/Init/Actions/Private"):
        world = private.find(".//WorldPosition")
        positions[private.get("entityRef")] = (
            float(world.get("x")),
            float(world.get("y")),
        )

    ego_x, ego_y = positions["Ego"]
    for actor in scenario.actors:
        ax, ay = positions[actor.id]
        exported = math.hypot(ax - ego_x, ay - ego_y)
        original = math.hypot(actor.x - scenario.ego.x, actor.y - scenario.ego.y)
        assert exported == pytest.approx(original, abs=1e-3)


def test_scenario_stops_at_the_declared_duration():
    scenario = SCENARIOS[0]
    root = ET.fromstring(export_scenario(scenario).xosc)
    stop = root.find("./Storyboard/StopTrigger//SimulationTimeCondition")
    assert stop is not None
    assert float(stop.get("value")) == pytest.approx(scenario.duration_s)


def test_trajectory_stride_shrinks_the_file_without_breaking_it():
    scenario = next(s for s in SCENARIOS if s.family.value in ("pedestrian", "vru_crossing"))
    dense = export_scenario(scenario, trajectory_stride=1)
    sparse = export_scenario(scenario, trajectory_stride=8)
    dense_vertices = len(ET.fromstring(dense.xosc).findall(".//Vertex"))
    sparse_vertices = len(ET.fromstring(sparse.xosc).findall(".//Vertex"))
    assert 0 < sparse_vertices < dense_vertices
    # The endpoint is always kept, so the actor still finishes where it should.
    last = ET.fromstring(sparse.xosc).findall(".//Vertex")[-1]
    assert float(last.get("time")) == pytest.approx(scenario.duration_s, abs=0.2)


# ---------------------------------------------------------------------------
# esmini
# ---------------------------------------------------------------------------


@needs_esmini
@pytest.mark.parametrize("scenario", SCENARIOS, ids=scenario_ids(SCENARIOS))
def test_scenario_runs_in_esmini(scenario, tmp_path):
    bundle = export_scenario(scenario)
    xosc_path, xodr_path = bundle.write(tmp_path)
    assert xodr_path.exists()
    run = run_esmini(xosc_path, timestep=scenario.timestep_s)
    assert run.ok, f"esmini rejected {scenario.id}: {run.errors}"


@needs_esmini
@pytest.mark.parametrize("scenario", SCENARIOS, ids=scenario_ids(SCENARIOS))
def test_trajectory_export_reproduces_the_simulation(scenario, tmp_path):
    """The claim that makes the benchmark reproducible elsewhere."""
    report = check_fidelity(
        scenario,
        tolerance_m=TRAJECTORY_POSITION_TOLERANCE_M,
        trajectory_mode=True,
        work_dir=tmp_path,
    )
    assert report.loaded, report.errors
    assert report.compared_samples > 0
    assert report.faithful, (
        f"{scenario.id} drifted {report.max_deviation_m:.4f} m "
        f"(worst per actor: {report.worst_by_actor})"
    )


@needs_esmini
def test_esmini_rejects_a_corrupted_scenario(tmp_path):
    """Guard the guard: validation must actually be able to fail."""
    bundle = export_scenario(SCENARIOS[0])
    xosc_path, _ = bundle.write(tmp_path)
    xosc_path.write_text(bundle.xosc.replace("</OpenSCENARIO>", ""))
    run = run_esmini(xosc_path, timestep=0.1)
    assert not run.ok
