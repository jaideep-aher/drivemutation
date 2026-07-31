"""Tests for t-way covering arrays and the ODD coverage guarantee.

The point of these tests is that the coverage claim is checkable.  Coverage is
verified with :func:`coverage_of`, which recomputes the target tuple set from
scratch rather than trusting the generator's own bookkeeping.
"""

from __future__ import annotations

import itertools

from backend.app.signalforge.catalog import build_catalog
from backend.app.signalforge.covering import (
    covering_array,
    coverage_of,
)
from backend.app.signalforge.expand import (
    achieved_coverage,
    catalog_coverage,
    expand_catalog,
    expand_logical,
    odd_forbidden,
    odd_space,
)
from backend.app.signalforge.schema import Weather


def test_pairwise_covers_every_pair():
    space = {
        "weather": ["clear", "rain", "fog"],
        "lighting": ["day", "dusk", "night"],
        "road": ["straight", "highway"],
        "decel": [3, 5, 7, 9],
    }
    rows, report = covering_array(space, strength=2)

    assert report.complete
    assert report.coverage_pct == 100.0

    # Independent brute-force check: every pair of parameters, every value
    # combination, must appear in some row.
    for a, b in itertools.combinations(space, 2):
        for va, vb in itertools.product(space[a], space[b]):
            assert any(
                r[a] == va and r[b] == vb for r in rows
            ), f"pair ({a}={va}, {b}={vb}) missing"


def test_pairwise_is_smaller_than_cartesian():
    space = {
        "weather": ["clear", "rain", "fog"],
        "lighting": ["day", "dusk", "night"],
        "road": ["straight", "highway"],
        "decel": [3, 5, 7, 9],
        "occlusion": ["none", "partial"],
    }
    rows, report = covering_array(space, strength=2)
    cartesian = 3 * 3 * 2 * 4 * 2
    assert report.complete
    # The whole point: full coverage of pairs at a fraction of the full product.
    assert len(rows) < cartesian / 4


def test_three_way_is_complete_and_larger_than_pairwise():
    space = {
        "a": [1, 2, 3],
        "b": ["x", "y"],
        "c": [True, False],
        "d": [10, 20, 30],
    }
    pair_rows, pair_report = covering_array(space, strength=2)
    triple_rows, triple_report = covering_array(space, strength=3)
    assert pair_report.complete and triple_report.complete
    assert len(triple_rows) > len(pair_rows)


def test_forbidden_combinations_are_never_emitted():
    space = {"weather": ["clear", "rain", "snow"], "surface": ["dry", "wet", "ice"]}

    def forbidden(row):
        return row["surface"] == "ice" and row["weather"] == "clear"

    rows, report = covering_array(space, strength=2, forbidden=forbidden)

    assert not any(forbidden(r) for r in rows)
    assert report.complete
    # The single ice+clear pair is unreachable, and is reported as such rather
    # than quietly counted as covered.
    assert report.unreachable == 1


def test_coverage_of_detects_a_hole():
    space = {"a": [1, 2], "b": ["x", "y"]}
    complete_rows = [
        {"a": 1, "b": "x"},
        {"a": 1, "b": "y"},
        {"a": 2, "b": "x"},
        {"a": 2, "b": "y"},
    ]
    assert coverage_of(complete_rows, space, strength=2).complete

    holed = complete_rows[:-1]
    report = coverage_of(holed, space, strength=2)
    assert not report.complete
    assert report.coverage_pct == 75.0
    assert report.missing == [(("a", 2), ("b", "y"))]


def test_generation_is_deterministic():
    space = {"a": [1, 2, 3], "b": ["x", "y"], "c": [True, False]}
    first, _ = covering_array(space, strength=2, seed=7)
    second, _ = covering_array(space, strength=2, seed=7)
    assert first == second


def test_degenerate_spaces():
    # No parameters at all: one empty assignment, not a crash.
    rows, report = covering_array({}, strength=2)
    assert rows == [{}]
    assert report.coverage_pct == 100.0

    # Strength above the parameter count clamps instead of raising.
    rows, report = covering_array({"a": [1, 2], "b": [3, 4]}, strength=9)
    assert report.strength == 2
    assert report.complete

    # A single parameter degrades to 1-way coverage of its values.
    rows, _ = covering_array({"a": [1, 2, 3]}, strength=2)
    assert {r["a"] for r in rows} == {1, 2, 3}

    # A parameter with no values is dropped rather than zeroing the space.
    rows, _ = covering_array({"a": [1, 2], "empty": []}, strength=2)
    assert rows and all("empty" not in r for r in rows)


def test_every_logical_scenario_reaches_full_pairwise_coverage():
    """The catalog-wide guarantee, measured on scenarios that survived feasibility."""
    for logical in build_catalog():
        scenarios = expand_logical(logical, samples_per_combo=2, seed=3, max_per_logical=400)
        assert scenarios, f"{logical.id} produced nothing"
        report = achieved_coverage(logical, scenarios)
        assert report.complete, (
            f"{logical.id} pairwise coverage {report.coverage_pct:.1f}% "
            f"missing {report.missing[:3]}"
        )


def test_expand_catalog_hits_target_with_full_coverage():
    logicals = build_catalog()
    scenarios = expand_catalog(logicals, target_count=2000, seed=42)

    assert len(scenarios) >= 2000
    ids = [s.id for s in scenarios]
    assert len(set(ids)) == len(ids), "concrete scenario ids must be unique"

    report = catalog_coverage(logicals, scenarios)
    assert report["complete"], report["incomplete_logicals"]
    assert report["coverage_pct"] == 100.0


def test_expand_catalog_is_deterministic():
    logicals = build_catalog()
    first = [s.id for s in expand_catalog(logicals, target_count=600, seed=11)]
    second = [s.id for s in expand_catalog(logicals, target_count=600, seed=11)]
    assert first == second


def test_ice_never_pairs_with_clear_weather_in_generated_scenarios():
    logical = next(s for s in build_catalog() if "surface" in s.odd_params)
    scenarios = expand_logical(logical, samples_per_combo=3, seed=5, max_per_logical=300)
    assert scenarios
    for sc in scenarios:
        if sc.odd.get("surface") == "ice":
            assert sc.weather != Weather.CLEAR


def test_odd_space_merges_environment_and_scenario_parameters():
    logical = next(s for s in build_catalog() if s.odd_params)
    space = odd_space(logical)
    assert {"weather", "lighting", "road_geometry"} <= set(space)
    for key in logical.odd_params:
        assert key in space
    # The forbidden predicate must be callable on any row of that space.
    forbidden = odd_forbidden(logical)
    sample = {k: v[0] for k, v in space.items()}
    assert isinstance(forbidden(sample), bool)
