"""Tests for the reference driver and the criticality search.

The central property being defended: criticality is a function of the scenario
and a published reference driver, never of a system under test, and the result
must be reproducible.
"""

from __future__ import annotations

import pytest

from backend.app.signalforge.catalog import catalog_by_id, simulable_catalog
from backend.app.signalforge.criticality import (
    AXES,
    boundary_scenarios,
    evaluate,
    layout_seed,
    search_catalog,
    search_logical,
)
from backend.app.signalforge.expand import _odd_combos, expand_logical
from backend.app.signalforge.reference_driver import (
    R157_MAX_DECEL_MPS2,
    R157_REACTION_S,
    R157_RISK_PERCEPTION_S,
    ReferenceDriver,
)
from backend.app.signalforge.sim import annotate_scenario, simulate


# ---------------------------------------------------------------------------
# Reference driver
# ---------------------------------------------------------------------------


def test_reference_driver_defaults_to_published_r157_values():
    driver = ReferenceDriver()
    assert driver.risk_perception_s == R157_RISK_PERCEPTION_S == 0.4
    assert driver.reaction_s == R157_REACTION_S == 0.75
    assert driver.max_decel_mps2 == R157_MAX_DECEL_MPS2 == 7.0
    assert driver.total_delay_s == pytest.approx(1.15)


def test_reaction_is_measured_from_the_hazard_not_the_scenario_start():
    """The bug this replaced: a hazard appearing late was reacted to instantly."""
    driver = ReferenceDriver()

    # Hazard becomes perceptible at t=3. The driver must not brake before 4.15.
    assert not driver.brakes_at(3.0, 3.0)
    assert not driver.brakes_at(3.0, 4.0)
    assert driver.brakes_at(3.0, 4.15)

    # A hazard that never became perceptible is never braked for.
    assert not driver.brakes_at(None, 99.0)


def test_driver_perception_threshold():
    driver = ReferenceDriver(perception_ttc_s=2.5)
    assert driver.perceives(1.0)
    assert not driver.perceives(3.0)
    assert not driver.perceives(None)


def test_driver_reads_regulatory_overrides_from_the_odd():
    driver = ReferenceDriver.from_odd({"risk_perception_s": 0.6, "reaction_s": 1.0})
    assert driver.risk_perception_s == 0.6
    assert driver.total_delay_s == pytest.approx(1.6)


def test_a_weaker_driver_never_does_better():
    """Sanity check on the yardstick: less braking cannot help."""
    logical = catalog_by_id()["nhtsa-25-lead-vehicle-decelerating"]
    row = _odd_combos(logical, seed=0)[0]
    params = {"ego_speed_kph": 90.0, "actor_speed_kph": 60.0, "distance_m": 25.0}

    strong = evaluate(logical, params, row, driver=ReferenceDriver(max_decel_mps2=9.0))
    weak = evaluate(logical, params, row, driver=ReferenceDriver(max_decel_mps2=3.0))
    assert weak.min_clearance_m <= strong.min_clearance_m


# ---------------------------------------------------------------------------
# Signed clearance
# ---------------------------------------------------------------------------


def test_clearance_is_negative_only_on_contact():
    for logical in simulable_catalog():
        batch = expand_logical(logical, samples_per_combo=1, seed=5, max_per_logical=2)
        for scenario in batch:
            result = simulate(scenario)
            clearance = result.metrics.min_clearance_m
            assert clearance is not None
            # The signed clearance and the collision flag must agree; if they
            # disagree the search objective is measuring something else.
            assert (clearance <= 0.0) == result.metrics.collision


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_layout_seed_is_stable_for_the_same_inputs():
    logical = catalog_by_id()["r157-cut-in"]
    row = {"relative_speed_kph": 0, "weather": "clear"}
    assert layout_seed(logical, row) == layout_seed(logical, dict(reversed(list(row.items()))))
    assert layout_seed(logical, row) != layout_seed(logical, {"relative_speed_kph": 10})


def test_evaluation_depends_only_on_its_parameters():
    """Otherwise bisection chases layout noise instead of the boundary."""
    logical = catalog_by_id()["nhtsa-12-pedestrian-without-prior-maneuver"]
    row = _odd_combos(logical, seed=0)[0]
    params = {"ego_speed_kph": 55.0, "actor_speed_kph": 6.0, "distance_m": 25.0}
    driver = ReferenceDriver()

    first = evaluate(logical, params, row, driver=driver, index=1)
    second = evaluate(logical, params, row, driver=driver, index=987)
    assert first.min_clearance_m == second.min_clearance_m
    assert first.collision == second.collision


def test_search_is_reproducible():
    logical = catalog_by_id()["r157-cut-in"]
    first = search_logical(logical, grid_steps=4, max_odd_rows=2)
    second = search_logical(logical, grid_steps=4, max_odd_rows=2)
    assert [s.as_dict() for s in first.boundary] == [s.as_dict() for s in second.boundary]
    assert first.evaluations == second.evaluations


def test_boundary_separates_survivable_from_unsurvivable():
    logical = catalog_by_id()["nhtsa-25-lead-vehicle-decelerating"]
    result = search_logical(logical, grid_steps=5, max_odd_rows=2)

    assert result.boundary, "expected a criticality boundary in the declared ranges"
    for sample in result.boundary:
        # A located boundary point is survivable, but only barely.
        assert sample.survivable
        assert sample.min_clearance_m < 1.0
        for axis in AXES:
            assert axis in sample.params


def test_boundary_points_stay_inside_the_declared_ranges():
    for logical_id in ("r157-cut-in", "nhtsa-12-pedestrian-without-prior-maneuver"):
        logical = catalog_by_id()[logical_id]
        result = search_logical(logical, grid_steps=4, max_odd_rows=2)
        for sample in result.boundary:
            assert (
                logical.ego_speed_kph.min - 1e-6
                <= sample.params["ego_speed_kph"]
                <= logical.ego_speed_kph.max + 1e-6
            )
            assert (
                logical.distance_m.min - 1e-6
                <= sample.params["distance_m"]
                <= logical.distance_m.max + 1e-6
            )


def test_search_reports_scenarios_with_no_boundary_rather_than_inventing_one():
    """A head-on with no escape has no boundary; saying so beats faking one."""
    logical = catalog_by_id()["hazop-wrong-way-intersection"]
    result = search_logical(logical, grid_steps=4, max_odd_rows=2)
    assert result.never_survivable
    assert result.boundary == []


def test_boundary_is_deduplicated():
    logical = catalog_by_id()["nhtsa-26-lead-vehicle-stopped"]
    result = search_logical(logical, grid_steps=4, max_odd_rows=4)
    keys = [tuple(round(s.params[a], 3) for a in AXES) for s in result.boundary]
    assert len(keys) == len(set(keys))


def test_catalog_search_covers_the_simulable_catalog():
    logicals = simulable_catalog()
    results = search_catalog(logicals, grid_steps=3, max_odd_rows=1)
    assert len(results) == len(logicals)
    assert all(r.evaluations > 0 for r in results)
    # Most scenarios should have a reachable boundary; if almost none do, the
    # objective or the ranges are wrong.
    with_boundary = [r for r in results if r.boundary]
    assert len(with_boundary) >= len(results) // 2


def test_boundary_scenarios_are_usable_concrete_scenarios():
    logicals = [catalog_by_id()["nhtsa-25-lead-vehicle-decelerating"]]
    results = search_catalog(logicals, grid_steps=4, max_odd_rows=1)
    scenarios = boundary_scenarios(results, logicals)

    assert scenarios
    for scenario in scenarios:
        assert scenario.metrics is not None
        assert scenario.difficulty is not None
        assert "criticality search" in scenario.provenance.notes
        # They must survive re-simulation and re-annotation like any scenario.
        annotate_scenario(scenario)
        assert scenario.metrics.min_clearance_m is not None
