"""Backend unit tests for DriveMutation Stage 1."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.presets import all_presets, get_preset, list_presets
from backend.app.schemas.scenario import ScenarioSpec
from backend.app.simulator import simulate
from backend.app.simulator.collision import OBB, boxes_overlap
from backend.app.simulator.metrics import relative_ttc
from backend.app.validators import validate_scenario


client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["deterministic"] is True


def test_presets_endpoint_lists_eight():
    r = client.get("/api/presets")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 8
    ids = {p["id"] for p in data}
    assert ids == {
        "occluded_pedestrian",
        "occluded_cyclist",
        "aggressive_cut_in",
        "unprotected_left_turn",
        "construction_lane_closure",
        "wrong_way_vehicle",
        "emergency_vehicle",
        "impossible_request",
    }
    by_id = {p["id"]: p for p in data}
    assert by_id["impossible_request"]["kind"] == "impossible"
    assert by_id["emergency_vehicle"]["default_testing_goal"]


def test_all_presets_validate_and_simulate():
    summaries = list_presets()
    assert len(summaries) == 8
    for preset in all_presets():
        issues = validate_scenario(preset)
        assert issues == [], f"{preset.id}: {issues}"
        result = simulate(preset)
        assert result.valid
        assert result.metrics is not None
        assert result.metrics.frame_count == int(round(preset.duration_s / 0.1)) + 1
        assert len(result.frames) == result.metrics.frame_count
        # Deterministic rounding: first frame t=0
        assert result.frames[0].t == 0.0


def test_deterministic_replay():
    scenario = get_preset("wrong_way_vehicle")
    a = simulate(scenario)
    b = simulate(scenario)
    assert a.model_dump() == b.model_dump()
    # API path
    payload = {"scenario": scenario.model_dump(mode="json")}
    r1 = client.post("/api/simulate", json=payload)
    r2 = client.post("/api/simulate", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()


def test_collision_detection_head_on():
    scenario = get_preset("wrong_way_vehicle")
    result = simulate(scenario)
    assert result.metrics is not None
    assert result.metrics.collision_count >= 1
    assert result.metrics.min_ttc is not None
    assert result.metrics.min_ttc >= 0.0


def test_ttc_helper_closing():
    ttc = relative_ttc(0, 0, 10, 0, 50, 0, 0, 0, 2.0)
    assert ttc is not None
    assert abs(ttc - 4.8) < 1e-6


def test_ttc_helper_receding():
    assert relative_ttc(0, 0, -10, 0, 50, 0, 0, 0, 2.0) is None


def test_boxes_overlap():
    a = OBB(0, 0, 4, 2, 0)
    b = OBB(3, 0, 4, 2, 0)
    c = OBB(10, 0, 4, 2, 0)
    assert boxes_overlap(a, b)
    assert not boxes_overlap(a, c)


def test_invalid_scenario_rejected_no_oracle():
    scenario = get_preset("occluded_pedestrian")
    data = scenario.model_dump(mode="json")
    data["oracles"] = []
    sc = ScenarioSpec.model_validate(data)
    issues = validate_scenario(sc)
    assert any(i.code == "no_oracle" for i in issues)
    r = client.post("/api/validate", json={"scenario": data})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False


def test_invalid_initial_collision():
    scenario = get_preset("occluded_pedestrian")
    data = scenario.model_dump(mode="json")
    # Place ped on top of ego
    data["actors"][1]["position"] = {"x": 5.0, "y": 0.0}
    data["actors"][1]["dimensions"] = {"length": 4.0, "width": 1.8}
    sc = ScenarioSpec.model_validate(data)
    issues = validate_scenario(sc)
    assert any(i.code == "initial_collision" for i in issues)


def test_speed_out_of_bounds():
    scenario = get_preset("occluded_pedestrian")
    data = scenario.model_dump(mode="json")
    data["ego"]["velocity"] = {"vx": 80.0, "vy": 0.0}
    sc = ScenarioSpec.model_validate(data)
    issues = validate_scenario(sc)
    assert any(i.code == "speed_out_of_bounds" for i in issues)


def test_simulate_rejects_invalid():
    scenario = get_preset("wrong_way_vehicle")
    data = scenario.model_dump(mode="json")
    data["oracles"] = []
    r = client.post("/api/simulate", json={"scenario": data})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["frames"] == []


def test_triggered_crossing_motion():
    scenario = get_preset("occluded_cyclist")
    result = simulate(scenario)
    # Cyclist should remain still until t=2.0 then move +y
    cyclist_traj = result.trajectories["cyclist"]
    # Frame at t=1.9 (index 19) still near start
    assert abs(cyclist_traj[19][1] - (-7.0)) < 0.05
    # After trigger, y increases
    assert cyclist_traj[-1][1] > cyclist_traj[20][1]


def test_contradictory_parked_ego():
    scenario = get_preset("occluded_pedestrian")
    data = scenario.model_dump(mode="json")
    data["ego"]["velocity"] = {"vx": 0.0, "vy": 0.0}
    data["ego"]["behavior"] = {"type": "parked"}
    sc = ScenarioSpec.model_validate(data)
    issues = validate_scenario(sc)
    assert any(i.code in {"contradictory_scenario", "unreachable_trigger"} for i in issues)


def test_api_preset_detail():
    r = client.get("/api/presets/aggressive_cut_in")
    assert r.status_code == 200
    assert r.json()["id"] == "aggressive_cut_in"
    r404 = client.get("/api/presets/does_not_exist")
    assert r404.status_code == 404
