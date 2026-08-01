"""Tests for the CA DMV disengagement ingest and the gap classification.

The property that matters here is honesty about what a gap is. An unmatched
narrative is only a candidate scenario gap if it describes a road situation; a
takeover for a software fault, or a narrative too vague to name a geometry, is
not evidence that the catalog is missing anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.signalforge.cadmv import (
    NARRATIVE_KEYS,
    classify_disengagements,
    is_non_scenario,
    is_unspecific,
    run_cadmv_pipeline,
    seed_disengagements,
    _lookup,
    _normalise,
)
from backend.app.signalforge.schema import ScenarioFamily
from backend.app.signalforge.sgo import classify_narrative


def test_dmv_headers_with_embedded_newlines_are_matched():
    """Real DMV headers wrap onto several lines and carry parenthetical hints."""
    row = {
        "DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "a pedestrian stepped into the road",
        "DISENGAGEMENT\nLOCATION\n(Interstate, Freeway, Highway)": "Street",
        "DRIVER PRESENT\n(Yes or No)": "Yes",
    }
    assert _normalise("DISENGAGEMENT\nLOCATION\n(Interstate, Freeway)") == "disengagement location"
    assert _lookup(row, NARRATIVE_KEYS) == "a pedestrian stepped into the road"


def test_internal_takeovers_are_not_scenario_gaps():
    assert is_non_scenario("Disengagement due to a software fault in the planner")
    assert is_non_scenario("Test driver disengaged at the end of route")
    assert is_non_scenario("Disengaged for GPS signal loss")
    # A real road situation is not internal.
    assert not is_non_scenario("A cyclist crossed in front of the vehicle")


def test_vague_narratives_are_flagged_rather_than_counted_as_gaps():
    """The largest class in the DMV data reports an outcome, not a geometry."""
    vague = (
        "The AV incorrectly predicted the behavior of another road user, which "
        "resulted in a motion plan requiring the safety driver to take control."
    )
    assert is_unspecific(vague)
    assert not is_unspecific("A pedestrian stepped off the curb ahead of the vehicle")


def test_new_catalog_families_are_classifiable():
    """Families added with the NHTSA typology need rules, or they can never match."""
    assert classify_narrative("debris in the roadway ahead") == ScenarioFamily.OBJECT
    assert classify_narrative("vehicle was backing out of a driveway") == ScenarioFamily.BACKING
    assert (
        classify_narrative("driver made an evasive maneuver to avoid it")
        == ScenarioFamily.EVASIVE_ACTION
    )
    assert (
        classify_narrative("a tire blowout caused loss of steering")
        == ScenarioFamily.VEHICLE_FAILURE
    )


def test_existing_classifications_are_unchanged():
    """Extending the rules must not re-route narratives that already matched."""
    assert classify_narrative("vehicle cut in abruptly ahead") == ScenarioFamily.CUT_IN
    assert classify_narrative("pedestrian crossed the street") == ScenarioFamily.PEDESTRIAN
    assert classify_narrative("bicycle entered the roadway") == ScenarioFamily.PEDALCYCLIST


def test_classification_splits_narratives_into_meaningful_buckets():
    rows = [
        {"DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "A pedestrian stepped into the crosswalk ahead."},
        {"DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "Disengaged due to a software fault in perception stack."},
        {"DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "The AV incorrectly predicted the behavior of another road user."},
        {"DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "Driver took over while negotiating an unusual roadside farmers market setup."},
        {"DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "short"},
    ]
    classified, gaps, weights = classify_disengagements(rows)

    # The too-short narrative is dropped entirely.
    assert len(classified) == 4

    by_narrative = {c["narrative"][:20]: c for c in classified}
    assert by_narrative["A pedestrian stepped"]["family"] == "pedestrian"
    assert by_narrative["Disengaged due to a "]["non_scenario"] is True
    assert by_narrative["The AV incorrectly p"]["unspecific"] is True

    # Only the specific, unmatched road situation is reported as a gap.
    assert len(gaps) == 1
    assert "farmers market" in gaps[0].narrative
    assert "CA DMV" in gaps[0].reason

    assert "_non_scenario_share" in weights
    assert "_unspecific_share" in weights


def test_vins_are_never_carried_into_the_output():
    """Disengagement CSVs contain VINs; they identify vehicles and are not needed."""
    rows = [
        {
            "Manufacturer": "Example AV",
            "VIN NUMBER": "1HGCM82633A004352",
            "DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": "A cyclist crossed ahead of the vehicle.",
        }
    ]
    classified, _, _ = classify_disengagements(rows)
    assert classified
    serialised = str(classified)
    assert "1HGCM82633A004352" not in serialised
    assert not any("vin" in key.lower() for key in classified[0])


def test_seed_fallback_is_marked_synthetic():
    """An offline demo must never pass invented narratives off as real reports."""
    classified, _, _ = classify_disengagements(seed_disengagements())
    assert classified
    assert all(c["synthetic"] for c in classified)
    assert all(c["source"] == "ca_dmv_disengagement" for c in classified)


def test_pipeline_falls_back_cleanly_when_offline(tmp_path: Path):
    """No network: the pipeline must still return a usable, clearly-marked result."""
    result = run_cadmv_pipeline(tmp_path, years=())
    assert result["source"] == "seed_synthetic"
    assert result["n_classified"] > 0
    assert all(c["synthetic"] for c in result["classified"])


def test_incident_ids_are_unique_and_source_tagged():
    rows = [
        {"DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": f"A pedestrian crossed at location {i}."}
        for i in range(20)
    ]
    classified, _, _ = classify_disengagements(rows)
    ids = [c["id"] for c in classified]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("cadmv-") for i in ids)
