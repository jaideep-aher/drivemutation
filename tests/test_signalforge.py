"""Smoke tests for SignalForge core pipeline."""

from __future__ import annotations

from backend.app.signalforge.catalog import build_catalog
from backend.app.signalforge.constraints import check_constraints, is_feasible
from backend.app.signalforge.expand import expand_logical
from backend.app.signalforge.lidar import actors_to_primitives, cast_lidar
from backend.app.signalforge.render import render_scenario
from backend.app.signalforge.sgo import classify_narrative, seed_incidents, classify_incidents
from backend.app.signalforge.schema import ScenarioFamily
from backend.app.signalforge.sim import annotate_scenario


def test_catalog_has_core_sources():
    cat = build_catalog()
    assert len(cat) >= 15
    sources = {s.provenance.source.value for s in cat}
    assert "nhtsa_precrash" in sources
    assert "unece_r157" in sources
    assert "euro_ncap" in sources


def test_expand_and_constrain():
    logical = build_catalog()[0]
    concrete = expand_logical(logical, samples_per_combo=1, seed=1, max_per_logical=5)
    assert len(concrete) >= 1
    for s in concrete:
        assert is_feasible(s)
        assert s.provenance.parent_id == logical.id


def test_sim_annotates_metrics():
    logical = next(s for s in build_catalog() if s.id == "r157-cut-in")
    concrete = expand_logical(logical, samples_per_combo=1, seed=7, max_per_logical=3)[0]
    annotate_scenario(concrete)
    assert concrete.metrics is not None
    assert concrete.difficulty is not None


def test_lidar_raycast_returns_points():
    prims = actors_to_primitives(
        {"x": 0, "y": 0},
        [{"actor_type": "vehicle", "x": 20, "y": 0, "length": 4.5, "width": 1.8, "height": 1.5, "heading_deg": 0, "vx": 0, "vy": 0}],
    )
    xyz, inten, sem, inst = cast_lidar(prims, n_beams=8, n_azimuth=64)
    assert len(xyz) > 10
    assert len(inten) == len(xyz)


def test_render_pipeline():
    logical = next(s for s in build_catalog() if s.family == ScenarioFamily.REAR_END)
    concrete = expand_logical(logical, samples_per_combo=1, seed=3, max_per_logical=2)[0]
    annotate_scenario(concrete)
    frames = render_scenario(concrete, max_frames=3, lidar_beams=8, lidar_azimuth=64)
    assert len(frames) >= 1
    assert len(frames[0].xyz) > 0


def test_sgo_classifier():
    assert classify_narrative("vehicle cut in abruptly ahead") == ScenarioFamily.CUT_IN
    assert classify_narrative("pedestrian crossed the street") == ScenarioFamily.PEDESTRIAN
    classified, gaps, weights = classify_incidents(seed_incidents())
    assert len(classified) == len(seed_incidents())
    assert weights
    # seed-020 should be a gap (balloon)
    assert any(g.incident_id == "seed-020" for g in gaps) or any(
        c["family"] == "unknown" for c in classified
    )


def test_pedestrian_speed_constraint():
    logical = next(s for s in build_catalog() if s.family == ScenarioFamily.PEDESTRIAN)
    concrete = expand_logical(logical, samples_per_combo=1, seed=11, max_per_logical=5)
    for s in concrete:
        # Feasible ones should not violate
        assert check_constraints(s) == [] or not is_feasible(s)
