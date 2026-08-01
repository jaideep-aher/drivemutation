"""Disk store for catalog, concrete scenarios, incidents, gaps, showcase."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.signalforge.schema import (
    ConcreteScenario,
    CoverageStats,
    GapItem,
    LogicalScenario,
    ScenarioSummary,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "signalforge"
CATALOG_PATH = DATA / "catalog" / "logical_scenarios.json"
CONCRETE_DIR = DATA / "concrete"
INCIDENTS_PATH = DATA / "incidents" / "classified.json"
GAPS_PATH = DATA / "gaps" / "gap_list.json"
SHOWCASE_DIR = DATA / "showcase"
WEIGHTS_PATH = DATA / "incidents" / "family_weights.json"


def ensure_dirs() -> None:
    for p in (DATA / "catalog", CONCRETE_DIR, DATA / "incidents", DATA / "gaps", SHOWCASE_DIR):
        p.mkdir(parents=True, exist_ok=True)


def save_catalog(logicals: list[LogicalScenario]) -> Path:
    ensure_dirs()
    payload = [s.model_dump(mode="json") for s in logicals]
    CATALOG_PATH.write_text(json.dumps(payload, indent=2))
    return CATALOG_PATH


def load_catalog() -> list[LogicalScenario]:
    if not CATALOG_PATH.exists():
        return []
    raw = json.loads(CATALOG_PATH.read_text())
    return [LogicalScenario.model_validate(x) for x in raw]


def save_concrete(scenarios: list[ConcreteScenario], *, clear: bool = True) -> int:
    ensure_dirs()
    if clear:
        for f in CONCRETE_DIR.glob("*.json"):
            f.unlink()
    # Shard into chunk files for faster listing
    chunk_size = 250
    count = 0
    index: list[dict] = []
    for i in range(0, len(scenarios), chunk_size):
        chunk = scenarios[i : i + chunk_size]
        path = CONCRETE_DIR / f"chunk_{i // chunk_size:04d}.json"
        path.write_text(json.dumps([s.model_dump(mode="json") for s in chunk]))
        for s in chunk:
            index.append(
                {
                    "id": s.id,
                    "logical_id": s.logical_id,
                    "family": s.family.value,
                    "name": s.name,
                    "weather": s.weather.value,
                    "lighting": s.lighting.value,
                    "road_geometry": s.road_geometry.value,
                    "difficulty": s.difficulty.value if s.difficulty else None,
                    "min_ttc_s": s.metrics.min_ttc_s if s.metrics else None,
                    "collision": s.metrics.collision if s.metrics else False,
                    "provenance_citation": s.provenance.citation,
                    "crash_frequency_weight": s.crash_frequency_weight,
                    "chunk": path.name,
                }
            )
            count += 1
    (CONCRETE_DIR / "index.json").write_text(json.dumps(index))
    return count


def load_index() -> list[dict]:
    path = CONCRETE_DIR / "index.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


_chunk_cache: dict[str, list[ConcreteScenario]] = {}


def load_concrete(scenario_id: str) -> ConcreteScenario | None:
    index = load_index()
    entry = next((e for e in index if e["id"] == scenario_id), None)
    if not entry:
        return None
    chunk_name = entry["chunk"]
    if chunk_name not in _chunk_cache:
        raw = json.loads((CONCRETE_DIR / chunk_name).read_text())
        _chunk_cache[chunk_name] = [ConcreteScenario.model_validate(x) for x in raw]
    for s in _chunk_cache[chunk_name]:
        if s.id == scenario_id:
            return s
    return None


def list_summaries(
    *,
    family: str | None = None,
    weather: str | None = None,
    difficulty: str | None = None,
    lighting: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ScenarioSummary]:
    index = load_index()
    out: list[ScenarioSummary] = []
    for e in index:
        if family and e["family"] != family:
            continue
        if weather and e["weather"] != weather:
            continue
        if difficulty and e.get("difficulty") != difficulty:
            continue
        if lighting and e["lighting"] != lighting:
            continue
        if q and q.lower() not in e["name"].lower() and q.lower() not in e["id"].lower():
            continue
        out.append(ScenarioSummary.model_validate(e))
    return out[offset : offset + limit]


def coverage_stats(gap_count: int = 0) -> CoverageStats:
    index = load_index()
    catalog = load_catalog()

    def count_by(key: str) -> dict[str, int]:
        d: dict[str, int] = {}
        for e in index:
            k = e.get(key) or "unknown"
            d[k] = d.get(k, 0) + 1
        return d

    return CoverageStats(
        total_concrete=len(index),
        total_logical=len(catalog),
        by_family=count_by("family"),
        by_weather=count_by("weather"),
        by_lighting=count_by("lighting"),
        by_difficulty=count_by("difficulty"),
        by_road=count_by("road_geometry"),
        gap_count=gap_count,
    )


COVERAGE_PATH = DATA / "catalog" / "odd_coverage.json"


def save_odd_coverage(report: dict) -> Path:
    """Persist the measured t-way ODD coverage of the generated set."""
    ensure_dirs()
    COVERAGE_PATH.write_text(json.dumps(report, indent=2))
    return COVERAGE_PATH


def load_odd_coverage() -> dict:
    if not COVERAGE_PATH.exists():
        return {}
    return json.loads(COVERAGE_PATH.read_text())


CRITICALITY_PATH = DATA / "catalog" / "criticality.json"


def save_criticality(report: dict) -> Path:
    """Persist the criticality-boundary search report."""
    ensure_dirs()
    CRITICALITY_PATH.write_text(json.dumps(report, indent=2))
    return CRITICALITY_PATH


def load_criticality() -> dict:
    if not CRITICALITY_PATH.exists():
        return {}
    return json.loads(CRITICALITY_PATH.read_text())


def save_gaps(gaps: list[GapItem]) -> None:
    ensure_dirs()
    GAPS_PATH.write_text(json.dumps([g.model_dump(mode="json") for g in gaps], indent=2))


def load_gaps() -> list[GapItem]:
    if not GAPS_PATH.exists():
        return []
    return [GapItem.model_validate(x) for x in json.loads(GAPS_PATH.read_text())]


def save_incidents(rows: list[dict]) -> None:
    ensure_dirs()
    INCIDENTS_PATH.write_text(json.dumps(rows, indent=2))


def load_incidents() -> list[dict]:
    if not INCIDENTS_PATH.exists():
        return []
    return json.loads(INCIDENTS_PATH.read_text())


def save_family_weights(weights: dict[str, float]) -> None:
    ensure_dirs()
    WEIGHTS_PATH.write_text(json.dumps(weights, indent=2))


def load_family_weights() -> dict[str, float]:
    if not WEIGHTS_PATH.exists():
        return {}
    return json.loads(WEIGHTS_PATH.read_text())


def save_showcase_frame(scenario_id: str, frames: list[dict]) -> Path:
    ensure_dirs()
    path = SHOWCASE_DIR / f"{scenario_id}.json"
    path.write_text(json.dumps(frames))
    return path


def load_showcase(scenario_id: str) -> list[dict] | None:
    path = SHOWCASE_DIR / f"{scenario_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
