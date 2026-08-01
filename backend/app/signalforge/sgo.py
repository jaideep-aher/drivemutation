"""NHTSA SGO ADS incident ingest and rule/LLM-assisted family classification."""

from __future__ import annotations

import csv
import io
import re
import urllib.request
from collections import Counter
from pathlib import Path

from backend.app.signalforge.schema import GapItem, ScenarioFamily

# Public NHTSA SGO dataset landing; try common CDN CSV mirrors / local fallback.
SGO_URLS = [
    # NHTSA open data portal mirrors change; we also ship a synthetic seed fallback.
    "https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_ADS.csv",
]

# Keyword rules mapping narrative -> family (deterministic, no API key required)
RULES: list[tuple[ScenarioFamily, list[str]]] = [
    (ScenarioFamily.CUT_IN, ["cut in", "cut-in", "merged into", "lane change into", "changed lanes into"]),
    (ScenarioFamily.CUT_OUT, ["cut out", "cut-out", "revealed", "pulled away revealing"]),
    (ScenarioFamily.DECELERATION, ["sudden stop", "hard brake", "abrupt deceler", "slammed on"]),
    (ScenarioFamily.REAR_END, ["rear-end", "rear end", "rearended", "struck from behind", "hit from behind", "front bumper", "rear bumper"]),
    (ScenarioFamily.PEDESTRIAN, ["pedestrian", "jaywalk", "person crossing", "walker"]),
    (ScenarioFamily.PEDALCYCLIST, ["bicycle", "bicyclist", "cyclist", "bike rider"]),
    (ScenarioFamily.VRU_CROSSING, ["scooter", "wheelchair", "skateboard"]),
    (ScenarioFamily.CROSSING_PATHS, ["intersection", "left turn", "ran red", "t-bone", "broadside", "crossing path"]),
    (ScenarioFamily.LANE_CHANGE, ["lane change", "side-swipe", "sideswipe", "adjacent lane"]),
    (ScenarioFamily.OPPOSITE_DIRECTION, ["wrong way", "oncoming", "head-on", "opposite direction"]),
    (ScenarioFamily.ROAD_DEPARTURE, [
        "left roadway", "road departure", "ran off", "shoulder", "curb",
        "lane boundary", "road edge", "lane marking", "drifting", "drifted",
    ]),
    (ScenarioFamily.CONTROL_LOSS, ["loss of control", "skid", "spin", "yaw"]),
    (ScenarioFamily.ANIMAL, ["deer", "animal", "dog in road", "wildlife"]),
    (ScenarioFamily.SENSOR_DEGRADATION, ["sensor", "lidar", "camera blocked", "perception", "visibility", "fog", "glare"]),
    # Families added with the full NHTSA typology. Without rules for these the
    # classifier could never assign them, and every matching narrative fell into
    # "unknown" and was reported as a catalog gap it is not.
    (ScenarioFamily.OBJECT, [
        "debris", "derbis", "object in the road", "object in road", "obstacle", "traffic cone",
        "cone in", "pothole", "tire tread", "foreign object", "fallen", "dropped load",
    ]),
    (ScenarioFamily.BACKING, ["backing", "reversing", "in reverse", "backed into", "reverse gear"]),
    (ScenarioFamily.EVASIVE_ACTION, ["evasive", "swerve", "swerved", "sudden maneuver", "abrupt maneuver"]),
    (ScenarioFamily.VEHICLE_FAILURE, [
        "tire blowout", "blowout", "mechanical failure", "component failure",
        "brake failure", "tire failure",
    ]),
]


def classify_narrative(text: str) -> ScenarioFamily:
    t = (text or "").lower()
    for family, keywords in RULES:
        for kw in keywords:
            if kw in t:
                return family
    return ScenarioFamily.UNKNOWN


def _parse_csv_text(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def download_sgo(dest: Path) -> list[dict]:
    """Try to download SGO CSV; on failure return empty and caller uses seed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for url in SGO_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SignalForge/0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            dest.write_bytes(data)
            # Try utf-8 then latin-1
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
            rows = _parse_csv_text(text)
            if rows:
                return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    if last_err:
        print(f"[sgo] download failed: {last_err}")
    return []


def seed_incidents() -> list[dict]:
    """Curated seed incidents inspired by public ADS crash patterns (for offline demo)."""
    seeds = [
        {
            "id": "seed-001",
            "Manufacturer": "Waymo",
            "Report Date": "2023-05-12",
            "Narrative": "ADS vehicle was rear-ended by a human-driven vehicle while stopped at a red light.",
        },
        {
            "id": "seed-002",
            "Manufacturer": "Cruise",
            "Report Date": "2023-08-02",
            "Narrative": "A pedestrian was struck after a collision redirected the path; incident involved intersection left turn conflict.",
        },
        {
            "id": "seed-003",
            "Manufacturer": "Zoox",
            "Report Date": "2024-01-18",
            "Narrative": "Another vehicle cut in abruptly ahead of the ADS, requiring hard braking.",
        },
        {
            "id": "seed-004",
            "Manufacturer": "Waymo",
            "Report Date": "2024-03-04",
            "Narrative": "Cyclist entered the roadway from the nearside crosswalk against signal.",
        },
        {
            "id": "seed-005",
            "Manufacturer": "Cruise",
            "Report Date": "2022-11-15",
            "Narrative": "Oncoming vehicle crossed centerline in opposite direction on a curve.",
        },
        {
            "id": "seed-006",
            "Manufacturer": "Mercedes-Benz",
            "Report Date": "2023-09-20",
            "Narrative": "Lead vehicle cut out of lane revealing a stopped disabled vehicle.",
        },
        {
            "id": "seed-007",
            "Manufacturer": "Zoox",
            "Report Date": "2024-06-01",
            "Narrative": "Heavy fog reduced camera visibility; sensor degradation contributed to delayed detection of a lead vehicle decelerating.",
        },
        {
            "id": "seed-008",
            "Manufacturer": "Waymo",
            "Report Date": "2023-02-11",
            "Narrative": "Sideswipe during parallel lane change by adjacent vehicle.",
        },
        {
            "id": "seed-009",
            "Manufacturer": "Cruise",
            "Report Date": "2022-07-30",
            "Narrative": "Deer entered roadway at night causing emergency maneuver.",
        },
        {
            "id": "seed-010",
            "Manufacturer": "Apple",
            "Report Date": "2023-12-08",
            "Narrative": "ADS vehicle lost traction on wet pavement and left roadway onto shoulder.",
        },
        {
            "id": "seed-011",
            "Manufacturer": "Nuro",
            "Report Date": "2024-02-14",
            "Narrative": "Construction worker with reflective vest caused lidar blooming near work zone; unusual roadside activity.",
        },
        {
            "id": "seed-012",
            "Manufacturer": "Cruise",
            "Report Date": "2023-10-02",
            "Narrative": "Fire truck emergency vehicle approached from behind with lights; ADS response delayed in urban canyon.",
        },
        {
            "id": "seed-013",
            "Manufacturer": "Waymo",
            "Report Date": "2024-04-22",
            "Narrative": "Lead vehicle slammed on brakes in highway traffic; sudden stop cascade.",
        },
        {
            "id": "seed-014",
            "Manufacturer": "Zoox",
            "Report Date": "2023-06-17",
            "Narrative": "Wrong-way driver entered one-way street toward ADS vehicle.",
        },
        {
            "id": "seed-015",
            "Manufacturer": "Cruise",
            "Report Date": "2024-05-09",
            "Narrative": "Scooter rider crossed mid-block without yielding.",
        },
        {
            "id": "seed-016",
            "Manufacturer": "Waymo",
            "Report Date": "2022-09-01",
            "Narrative": "Vehicle ran red light at intersection resulting in broadside contact.",
        },
        {
            "id": "seed-017",
            "Manufacturer": "Mercedes-Benz",
            "Report Date": "2023-04-19",
            "Narrative": "Low sun glare saturated forward cameras during dusk cut-in event.",
        },
        {
            "id": "seed-018",
            "Manufacturer": "Zoox",
            "Report Date": "2024-07-11",
            "Narrative": "Parked delivery van occluded a child pedestrian who then entered the roadway.",
        },
        {
            "id": "seed-019",
            "Manufacturer": "Cruise",
            "Report Date": "2023-01-25",
            "Narrative": "ADS contacted a curb after avoiding a double-parked vehicle; road edge departure.",
        },
        {
            "id": "seed-020",
            "Manufacturer": "Waymo",
            "Report Date": "2024-08-03",
            "Narrative": "Unknown aerial object / balloon drifted into roadway — no clear catalog match for floating debris.",
        },
    ]
    return seeds


def _narrative_from_row(row: dict) -> str:
    for key in (
        "Narrative",
        "narrative",
        "Incident Narrative",
        "Description",
        "Crash Description",
        "ADS Narrative",
        "Incident Description",
    ):
        if key in row and row[key]:
            return str(row[key])
    # Concatenate any long text fields
    parts = []
    for k, v in row.items():
        if v and isinstance(v, str) and len(v) > 40:
            parts.append(v)
    return " ".join(parts)[:2000]


def _id_from_row(row: dict, idx: int) -> str:
    for key in ("Report ID", "ID", "id", "Incident ID", "NHTSA ID"):
        if key in row and row[key]:
            return str(row[key])
    return f"sgo-{idx:05d}"


def classify_incidents(rows: list[dict]) -> tuple[list[dict], list[GapItem], dict[str, float]]:
    classified: list[dict] = []
    gaps: list[GapItem] = []
    counts: Counter[str] = Counter()

    for i, row in enumerate(rows):
        narrative = _narrative_from_row(row)
        if not narrative or len(narrative) < 10:
            continue
        family = classify_narrative(narrative)
        iid = _id_from_row(row, i)
        manufacturer = str(row.get("Manufacturer") or row.get("Reporting Entity") or "")
        date = str(row.get("Report Date") or row.get("Incident Date") or "")
        rec = {
            "id": iid,
            "manufacturer": manufacturer,
            "date": date,
            "narrative": narrative[:1500],
            "family": family.value,
        }
        classified.append(rec)
        counts[family.value] += 1
        if family == ScenarioFamily.UNKNOWN:
            gaps.append(
                GapItem(
                    incident_id=iid,
                    narrative=narrative[:800],
                    manufacturer=manufacturer,
                    date=date,
                    reason="no matching catalog family",
                )
            )

    total = sum(counts.values()) or 1
    weights = {k: v / total for k, v in counts.items()}
    return classified, gaps, weights


def run_sgo_pipeline(data_dir: Path) -> dict:
    raw_path = data_dir / "incidents" / "sgo_raw.csv"
    rows = download_sgo(raw_path)
    source = "nhtsa_sgo_download"
    if not rows:
        rows = seed_incidents()
        source = "seed_curated"
    classified, gaps, weights = classify_incidents(rows)
    return {
        "source": source,
        "n_raw": len(rows),
        "n_classified": len(classified),
        "n_gaps": len(gaps),
        "classified": classified,
        "gaps": gaps,
        "weights": weights,
    }
