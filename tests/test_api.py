"""Tests for the SignalForge HTTP API.

Distinct from ``test_backend.py``, which targets the superseded pre-SignalForge
mutation API.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.signalforge import store

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not store.load_index(),
    reason="no generated scenarios; run scripts/generate_signalforge.py",
)


@pytest.fixture(scope="module")
def a_scenario_id() -> str:
    rows = client.get("/api/scenarios?limit=1").json()
    assert rows, "expected at least one scenario in the store"
    return rows[0]["id"]


def test_health_reports_catalog_size():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["concrete_count"] > 0
    assert body["logical_count"] > 0


def test_scenario_count_matches_the_listing():
    """The list pages; without a matching total it cannot say how far it got."""
    total = client.get("/api/scenarios/count").json()["count"]
    assert total > 0

    page = client.get("/api/scenarios?limit=10&offset=0").json()
    assert len(page) == min(10, total)

    # A filter must narrow both the listing and the count consistently.
    family = page[0]["family"]
    filtered_count = client.get(f"/api/scenarios/count?family={family}").json()["count"]
    filtered_page = client.get(f"/api/scenarios?family={family}&limit=500").json()
    assert 0 < filtered_count <= total
    assert all(row["family"] == family for row in filtered_page)
    assert len(filtered_page) == min(500, filtered_count)


def test_scenario_count_honours_search_and_lighting():
    all_count = client.get("/api/scenarios/count").json()["count"]
    lit = client.get("/api/scenarios/count?lighting=night").json()["count"]
    searched = client.get("/api/scenarios/count?q=pedestrian").json()["count"]
    assert 0 <= lit <= all_count
    assert 0 <= searched <= all_count


def test_paging_walks_the_list_without_repeats():
    page_one = client.get("/api/scenarios?limit=25&offset=0").json()
    page_two = client.get("/api/scenarios?limit=25&offset=25").json()
    ids_one = {row["id"] for row in page_one}
    ids_two = {row["id"] for row in page_two}
    assert ids_one and ids_two
    assert not (ids_one & ids_two), "pages must not overlap"


def test_openscenario_download_is_a_self_contained_bundle(a_scenario_id):
    response = client.get(f"/api/scenarios/{a_scenario_id}/openscenario")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert a_scenario_id in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert f"{a_scenario_id}.xosc" in names
    assert f"{a_scenario_id}.xodr" in names

    xosc = archive.read(f"{a_scenario_id}.xosc").decode()
    root = ET.fromstring(xosc)
    assert root.tag == "OpenSCENARIO"
    # The road must be referenced by bare filename so the pair works anywhere.
    logic = root.find("./RoadNetwork/LogicFile")
    assert logic is not None
    assert logic.get("filepath") == f"{a_scenario_id}.xodr"
    assert root.find(".//CatalogReference") is None

    ET.fromstring(archive.read(f"{a_scenario_id}.xodr").decode())


def test_openscenario_download_supports_trajectory_mode(a_scenario_id):
    response = client.get(
        f"/api/scenarios/{a_scenario_id}/openscenario?trajectory_mode=true"
    )
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    ET.fromstring(archive.read(f"{a_scenario_id}.xosc").decode())


def test_openscenario_download_404s_for_unknown_scenario():
    assert client.get("/api/scenarios/does-not-exist/openscenario").status_code == 404


def test_odd_coverage_endpoint_reports_a_measured_guarantee():
    body = client.get("/api/coverage/odd").json()
    assert body["strength"] >= 2
    assert body["reachable_tuples"] > 0
    assert 0 <= body["coverage_pct"] <= 100
    assert body["covered_tuples"] <= body["reachable_tuples"]


def test_coverage_lists_every_generated_family():
    coverage = client.get("/api/coverage").json()
    families = set(coverage["by_family"])
    listed = {
        row["family"] for row in client.get("/api/scenarios?limit=500").json()
    }
    assert listed <= families
