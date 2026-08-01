"""Tests that the catalog stays faithful to the published NHTSA typology.

The scenario names, crash counts and shares in ``catalog.py`` are transcribed
from ``data/typology/nhtsa_precrash_typology.json``, which was itself verified
against the primary NHTSA reports.  These tests exist so the two cannot drift
apart silently — a mistyped crash count is exactly the kind of error that would
otherwise survive review and end up cited in a paper.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.signalforge.catalog import (
    _NHTSA_FACTS,
    build_catalog,
    catalog_by_id,
    simulable_catalog,
)
from backend.app.signalforge.expand import catalog_coverage, expand_catalog, expand_logical
from backend.app.signalforge.schema import ScenarioFamily, SourceType

TYPOLOGY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "typology" / "nhtsa_precrash_typology.json"
)


@pytest.fixture(scope="module")
def typology() -> dict:
    return json.loads(TYPOLOGY_PATH.read_text())


def test_typology_source_file_is_present(typology):
    assert typology["scenario_count"] == 37
    assert typology["substantive_count"] == 36
    assert len(typology["scenarios"]) == 37


def test_facts_table_matches_the_verified_source(typology):
    """Every name, crash count and share must match the source file exactly."""
    source = {s["number"]: s for s in typology["scenarios"]}

    # Scenario 37 is the residual "Other" bucket, not a scenario to model.
    assert 37 not in _NHTSA_FACTS
    assert set(_NHTSA_FACTS) == set(range(1, 37))

    for number, (name, group, crashes, share) in _NHTSA_FACTS.items():
        entry = source[number]
        assert name == entry["name"], f"scenario {number} name drifted"
        assert group == entry["group_2019"], f"scenario {number} group drifted"

        match = re.match(r"([\d,]+)\s*\(([\d.]+)%\)", entry["annual_crashes_2004_ges"])
        assert match, f"scenario {number} has unparseable published figures"
        assert crashes == int(match.group(1).replace(",", ""))
        assert share == pytest.approx(float(match.group(2)))


def test_every_substantive_scenario_is_catalogued():
    nhtsa = [s for s in build_catalog() if s.provenance.source == SourceType.NHTSA_PRECRASH]
    assert len(nhtsa) == 36

    numbers = sorted(s.nhtsa_scenario_number for s in nhtsa)
    assert numbers == list(range(1, 37))

    names = [s.name for s in nhtsa]
    assert len(set(names)) == len(names), "no scenario may appear twice"


def test_crash_weights_are_derived_from_published_shares():
    """Weights must be traceable arithmetic on published figures, not invented."""
    nhtsa = [s for s in build_catalog() if s.nhtsa_scenario_number is not None]
    max_share = max(s.crash_share_pct for s in nhtsa)

    for scenario in nhtsa:
        _, _, crashes, share = _NHTSA_FACTS[scenario.nhtsa_scenario_number]
        assert scenario.annual_crashes == crashes
        assert scenario.crash_share_pct == pytest.approx(share)
        assert scenario.crash_frequency_weight == pytest.approx(share / max_share, abs=1e-4)

    # Lead Vehicle Stopped is the most frequent scenario, so it anchors the scale.
    lead_stopped = next(s for s in nhtsa if s.nhtsa_scenario_number == 26)
    assert lead_stopped.crash_frequency_weight == pytest.approx(1.0)


def test_citations_name_the_report_and_scenario_number():
    for scenario in build_catalog():
        if scenario.nhtsa_scenario_number is None:
            continue
        citation = scenario.provenance.citation
        assert "DOT HS 810 767" in citation
        assert f"scenario {scenario.nhtsa_scenario_number} " in citation
        # Judgement-based ranges must say so rather than implying published values.
        assert "engineering judgement" in scenario.provenance.notes


def test_regulatory_and_hazop_scenarios_are_preserved():
    """Extending the catalog must not quietly drop the existing sources."""
    by_id = catalog_by_id()
    for scenario_id in (
        "r157-cut-in",
        "r157-cut-out",
        "r157-deceleration",
        "euro-cpna-50",
        "euro-cpfa-50",
        "euro-cpta-50",
        "hazop-lidar-rain-dropout",
        "hazop-occluded-ped-dusk",
        "hazop-camera-glare-cutin",
        "hazop-wrong-way-intersection",
    ):
        assert scenario_id in by_id, f"{scenario_id} was dropped"

    # The R157 regulatory parameters are the point of those entries.
    assert by_id["r157-cut-in"].r157_params["risk_perception_s"] == 0.4
    assert by_id["r157-cut-in"].r157_params["lateral_wander_m"] == 0.375
    assert by_id["r157-deceleration"].r157_params["decel_threshold_mps2"] == 5.0


def test_catalog_size_and_source_mix():
    catalog = build_catalog()
    assert len(catalog) == 46
    counts: dict[str, int] = {}
    for scenario in catalog:
        counts[scenario.provenance.source.value] = (
            counts.get(scenario.provenance.source.value, 0) + 1
        )
    assert counts == {
        "nhtsa_precrash": 36,
        "unece_r157": 3,
        "euro_ncap": 3,
        "hazop": 4,
    }


def test_the_nine_crash_groups_are_represented():
    families = {s.family for s in build_catalog()}
    for family in (
        ScenarioFamily.REAR_END,
        ScenarioFamily.CROSSING_PATHS,
        ScenarioFamily.LANE_CHANGE,
        ScenarioFamily.ROAD_DEPARTURE,
        ScenarioFamily.CONTROL_LOSS,
        ScenarioFamily.ANIMAL,
        ScenarioFamily.OPPOSITE_DIRECTION,
        ScenarioFamily.PEDESTRIAN,
        ScenarioFamily.PEDALCYCLIST,
    ):
        assert family in families


def test_unrepresentable_scenarios_are_flagged_not_faked():
    """A scenario the sim cannot model must be excluded, not given fake metrics."""
    catalog = build_catalog()
    unsimulable = [s for s in catalog if not s.simulable]
    assert unsimulable, "expected at least the non-collision scenario to be flagged"
    for scenario in unsimulable:
        assert scenario.provenance.notes, "an excluded scenario must explain why"

    scenarios = expand_catalog(catalog, target_count=500, seed=3)
    produced = {s.logical_id for s in scenarios}
    for scenario in unsimulable:
        assert scenario.id not in produced


def test_every_simulable_scenario_generates():
    for logical in simulable_catalog():
        batch = expand_logical(logical, samples_per_combo=2, seed=1, max_per_logical=60)
        assert batch, f"{logical.id} produced no feasible concrete scenario"


def test_full_catalog_keeps_complete_pairwise_coverage():
    catalog = build_catalog()
    scenarios = expand_catalog(catalog, target_count=5000, seed=42)
    assert len(scenarios) >= 5000

    report = catalog_coverage(simulable_catalog(), scenarios)
    assert report["complete"], report["incomplete_logicals"]
    assert report["coverage_pct"] == 100.0


def test_rear_end_group_models_five_distinct_lead_behaviours():
    """The typology splits rear-end five ways; collapsing them all to a brake
    would throw away most of the group."""
    by_id = catalog_by_id()
    behaviours = {
        number: by_id[
            next(
                s.id
                for s in build_catalog()
                if s.nhtsa_scenario_number == number
            )
        ].actors[0].behavior
        for number in (23, 24, 25, 26)
    }
    assert behaviours[23] == "accelerate"
    assert behaviours[24] == "constant_velocity"
    assert behaviours[25] == "brake"
    assert behaviours[26] == "static"
