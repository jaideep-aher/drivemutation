"""California DMV autonomous-vehicle disengagement report ingest.

NHTSA's SGO dataset records crashes. California's disengagement reports record
something different and, for finding catalog gaps, arguably more useful: every
time a test driver or the system itself handed control back. A disengagement is
a near miss the vehicle chose not to attempt — the situation an ADS met and
declined — so a disengagement narrative with no matching catalog family is
direct evidence of a scenario the catalog does not cover.

The two sources are ingested through the same classifier but kept distinct
downstream, because their base rates mean different things. Crash counts speak
to real-world frequency; disengagement counts speak to operational difficulty and
are confounded by fleet size, testing policy and how conservatively each operator
sets its handover thresholds. Averaging them together would produce a number that
means nothing.

Published by the California DMV under the autonomous vehicle testing regulations
(13 CCR §227.46).
"""

from __future__ import annotations

import csv
import io
import re
import urllib.request
from collections import Counter
from pathlib import Path

from backend.app.signalforge.schema import GapItem, ScenarioFamily
from backend.app.signalforge.sgo import classify_narrative

#: Disengagement report CSVs, newest first. The DMV publishes one per reporting
#: year; years that 404 are skipped rather than treated as an error.
CADMV_YEARS = (2024, 2023, 2022, 2021, 2020)

CADMV_URL_TEMPLATE = (
    "https://www.dmv.ca.gov/portal/file/"
    "{year}-autonomous-vehicle-disengagement-reports-csv/"
)

#: Column headers in these files carry embedded newlines and inconsistent
#: casing between years, so columns are matched on a normalised form.
NARRATIVE_KEYS = (
    "description of facts causing disengagement",
    "description of facts causing the disengagement",
    "disengagement description",
)
MANUFACTURER_KEYS = ("manufacturer", "company name")
DATE_KEYS = ("date", "month", "date of disengagement")
LOCATION_KEYS = ("disengagement location", "location")
INITIATED_BY_KEYS = ("disengagement initiated by", "initiated by")

#: Never carried into the output. VINs identify individual vehicles and are of
#: no analytical use here.
DROP_KEYS = ("vin number", "vin", "permit number")


#: Disengagements caused by the vehicle's own software, hardware or test
#: administration rather than by anything happening on the road.
#:
#: This distinction matters for honesty. A narrative the classifier cannot place
#: is not automatically a missing scenario — a takeover for a diagnostic fault or
#: at the end of a planned test route says nothing about catalog coverage.
#: Counting those as gaps would inflate the gap report with material no scenario
#: catalog could ever address.
NON_SCENARIO_PATTERNS = (
    "software",
    "hardware",
    "system fault",
    "diagnostic",
    "planned",
    "end of route",
    "end of test",
    "testing purposes",
    "test complete",
    "conclusion of the test",
    "localization",
    "localisation",
    "gps",
    "map data",
    "mapping",
    "connectivity",
    "wireless",
    "communication loss",
    "calibration",
    "operator error",
    "manual takeover for shift",
    "recording",
)


#: Boilerplate that reports *that* an interaction went wrong without saying what
#: the other road user actually did.
#:
#: This is the largest single class of narrative in the CA DMV files. Phrasing
#: like "the AV incorrectly predicted the behavior of another road user, which
#: resulted in a motion plan requiring the safety driver to take control"
#: describes an outcome, not a geometry — there is no way to tell a cut-in from a
#: crossing conflict from an unprotected turn. These are scenario-relevant but
#: unclassifiable, which is a limitation of the reporting, not evidence that the
#: catalog is missing anything. Reporting them as gaps would be wrong in both
#: directions: it would overstate the gap count and hide the real finding, which
#: is that most disengagement reporting is too vague to mine.
UNSPECIFIC_PATTERNS = (
    "another road user",
    "other road user",
    "motion plan",
    "predicted the behavior",
    "predicted the behaviour",
    "perception discrepancy",
    "incorrectly predicted",
    "undesirable motion",
)


def is_non_scenario(text: str) -> bool:
    """Whether a disengagement is internal rather than caused by the road."""
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in NON_SCENARIO_PATTERNS)


def is_unspecific(text: str) -> bool:
    """Whether a narrative reports an interaction without describing it."""
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in UNSPECIFIC_PATTERNS)


def _normalise(key: str) -> str:
    """Collapse whitespace and drop the parenthetical hints in DMV headers."""
    without_hint = re.sub(r"\(.*?\)", " ", key or "", flags=re.S)
    return re.sub(r"\s+", " ", without_hint).strip().lower()


def _lookup(row: dict, candidates: tuple[str, ...]) -> str:
    normalised = {_normalise(k): v for k, v in row.items()}
    for candidate in candidates:
        value = normalised.get(candidate)
        if value:
            return str(value).strip()
    # Fall back to a prefix match, since headers drift between reporting years.
    for key, value in normalised.items():
        if value and any(key.startswith(c[:24]) for c in candidates):
            return str(value).strip()
    return ""


def _parse_csv_text(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def download_year(year: int, dest_dir: Path) -> list[dict]:
    """Fetch one reporting year, returning [] when it is unavailable."""
    url = CADMV_URL_TEMPLATE.format(year=year)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SignalForge/0.1"})
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
    except Exception as exc:  # noqa: BLE001 - unavailable years are expected
        print(f"[cadmv] {year} unavailable: {exc}")
        return []

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")

    rows = _parse_csv_text(text)
    if not rows:
        return []

    (dest_dir / f"cadmv_disengagement_{year}.csv").write_bytes(data)
    for row in rows:
        row["_report_year"] = str(year)
    return rows


def download_cadmv(dest_dir: Path, years: tuple[int, ...] = CADMV_YEARS) -> list[dict]:
    """Fetch every available reporting year."""
    rows: list[dict] = []
    for year in years:
        rows.extend(download_year(year, dest_dir))
    return rows


def seed_disengagements() -> list[dict]:
    """Offline fallback, paraphrasing the shape of real disengagement narratives.

    Clearly synthetic, and only used when the DMV files cannot be reached, so a
    demo still runs. Never presented as real reports.
    """
    samples = [
        ("Waymo LLC", "Street", "Test driver disengaged when a pedestrian stepped off the curb mid-block ahead of the vehicle."),
        ("Cruise LLC", "Street", "AV system disengaged due to a cyclist approaching from the right at an uncontrolled intersection."),
        ("Zoox Inc.", "Freeway", "Test driver took over when a vehicle ahead braked hard in heavy traffic."),
        ("Nuro Inc.", "Street", "Disengagement after another vehicle cut in closely from the adjacent lane."),
        ("Apple Inc.", "Highway", "Test driver disengaged because of debris in the roadway."),
        ("Mercedes-Benz", "Freeway", "Disengaged for an oncoming vehicle drifting across the centerline."),
        ("AImotive", "Street", "Safety driver disengaged due to unclear lane markings in construction zone."),
        ("Argo AI", "Street", "Disengagement caused by an emergency vehicle approaching with lights and siren."),
        ("Motional", "Parking Facility", "Test driver took over while manoeuvring around a double-parked delivery truck."),
        ("Pony.ai", "Street", "Disengaged when a traffic officer manually directed traffic through the intersection."),
    ]
    return [
        {
            "Manufacturer": manufacturer,
            "DATE": "2023-01-01",
            "DISENGAGEMENT LOCATION": location,
            "DESCRIPTION OF FACTS CAUSING DISENGAGEMENT": narrative,
            "_report_year": "seed",
            "_synthetic": "true",
        }
        for manufacturer, location, narrative in samples
    ]


def classify_disengagements(
    rows: list[dict],
) -> tuple[list[dict], list[GapItem], dict[str, float]]:
    """Classify disengagement narratives into catalog families.

    Returns the classified records, the ones with no matching family (candidate
    gaps), and the family distribution. That distribution describes *operational
    difficulty*, not crash frequency — see the module docstring.
    """
    classified: list[dict] = []
    gaps: list[GapItem] = []
    counts: Counter[str] = Counter()
    non_scenario = 0
    unspecific = 0

    for i, row in enumerate(rows):
        narrative = _lookup(row, NARRATIVE_KEYS)
        if not narrative or len(narrative) < 10:
            continue

        internal = is_non_scenario(narrative)
        vague = is_unspecific(narrative)
        if internal:
            non_scenario += 1
        if vague:
            unspecific += 1
        family = classify_narrative(narrative)
        manufacturer = _lookup(row, MANUFACTURER_KEYS)
        date = _lookup(row, DATE_KEYS)
        year = str(row.get("_report_year", ""))
        incident_id = f"cadmv-{year}-{i:05d}"

        classified.append(
            {
                "id": incident_id,
                "source": "ca_dmv_disengagement",
                "manufacturer": manufacturer,
                "date": date,
                "location": _lookup(row, LOCATION_KEYS),
                "initiated_by": _lookup(row, INITIATED_BY_KEYS),
                "narrative": narrative[:1500],
                "family": family.value,
                "non_scenario": internal,
                "unspecific": vague,
                "synthetic": row.get("_synthetic") == "true",
            }
        )
        counts[family.value] += 1

        # Only an unmatched narrative describing something on the road is a
        # candidate scenario gap.
        if family == ScenarioFamily.UNKNOWN and not internal and not vague:
            gaps.append(
                GapItem(
                    incident_id=incident_id,
                    narrative=narrative[:800],
                    manufacturer=manufacturer,
                    date=date,
                    reason="no matching catalog family (CA DMV disengagement)",
                )
            )

    total = sum(counts.values()) or 1
    weights = {k: v / total for k, v in counts.items()}
    weights["_non_scenario_share"] = non_scenario / total
    weights["_unspecific_share"] = unspecific / total
    return classified, gaps, weights


def run_cadmv_pipeline(data_dir: Path, years: tuple[int, ...] = CADMV_YEARS) -> dict:
    """Download, classify and summarise the CA DMV disengagement reports."""
    rows = download_cadmv(data_dir / "incidents", years=years)
    source = "ca_dmv_download"
    if not rows:
        rows = seed_disengagements()
        source = "seed_synthetic"

    classified, gaps, weights = classify_disengagements(rows)
    years_seen = sorted({r.get("_report_year", "") for r in rows if r.get("_report_year")})

    return {
        "source": source,
        "years": years_seen,
        "n_raw": len(rows),
        "n_classified": len(classified),
        "n_non_scenario": sum(1 for c in classified if c["non_scenario"]),
        "n_unspecific": sum(1 for c in classified if c["unspecific"]),
        "n_gaps": len(gaps),
        "classified": classified,
        "gaps": gaps,
        "weights": weights,
    }
