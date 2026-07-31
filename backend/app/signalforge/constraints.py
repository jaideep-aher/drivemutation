"""Physical and semantic constraint checks for concrete scenarios."""

from __future__ import annotations

from backend.app.signalforge.schema import ConcreteScenario, Weather


MAX_PEDESTRIAN_SPEED_KPH = 12.0
MAX_CYCLIST_SPEED_KPH = 40.0
MAX_ANIMAL_SPEED_KPH = 50.0
MAX_VEHICLE_SPEED_KPH = 160.0
MIN_DISTANCE_M = 1.0


def _speed_kph(vx: float, vy: float) -> float:
    return (vx * vx + vy * vy) ** 0.5 * 3.6


def check_constraints(scenario: ConcreteScenario) -> list[str]:
    """Return list of violation messages; empty means feasible."""
    violations: list[str] = []

    ego_spd = _speed_kph(scenario.ego.vx, scenario.ego.vy)
    if ego_spd > MAX_VEHICLE_SPEED_KPH:
        violations.append(f"ego speed {ego_spd:.1f} kph exceeds max")

    for actor in scenario.actors:
        spd = _speed_kph(actor.vx, actor.vy)
        if actor.actor_type == "pedestrian" and spd > MAX_PEDESTRIAN_SPEED_KPH:
            violations.append(f"{actor.id} pedestrian speed {spd:.1f} kph unrealistic")
        if actor.actor_type == "cyclist" and spd > MAX_CYCLIST_SPEED_KPH:
            violations.append(f"{actor.id} cyclist speed {spd:.1f} kph unrealistic")
        if actor.actor_type == "animal" and spd > MAX_ANIMAL_SPEED_KPH:
            violations.append(f"{actor.id} animal speed {spd:.1f} kph unrealistic")
        if actor.actor_type == "vehicle" and spd > MAX_VEHICLE_SPEED_KPH:
            violations.append(f"{actor.id} vehicle speed {spd:.1f} kph exceeds max")

        dx = actor.x - scenario.ego.x
        dy = actor.y - scenario.ego.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < MIN_DISTANCE_M and actor.actor_type != "static":
            # Allow parked occlusion helpers close by
            if actor.behavior != "static":
                violations.append(f"{actor.id} starts too close to ego ({dist:.2f} m)")

    # Ice only makes sense in cold weather; we model ice via rain/snow
    surface = scenario.odd.get("surface")
    if surface == "ice" and scenario.weather not in (Weather.SNOW, Weather.RAIN, Weather.FOG):
        # Allow ice with snow primarily; soft reject clear+ice
        if scenario.weather == Weather.CLEAR:
            violations.append("ice surface incompatible with clear weather")

    # Cut-in needs lateral offset (adjacent lane)
    if scenario.family.value in ("cut_in", "lane_change"):
        for actor in scenario.actors:
            if abs(actor.y - scenario.ego.y) < 1.5 and actor.behavior == "cut_in":
                violations.append(f"{actor.id} cut-in without adjacent-lane offset")

    # Lane count for lane change
    if scenario.family.value == "lane_change":
        lanes = scenario.odd.get("lane_count")
        if lanes is not None and int(lanes) < 2:
            violations.append("lane_change requires at least 2 lanes")

    return violations


def is_feasible(scenario: ConcreteScenario) -> bool:
    return len(check_constraints(scenario)) == 0
