"""Bicycle-model kinematic simulator with criticality metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.app.signalforge.reference_driver import ReferenceDriver
from backend.app.signalforge.schema import (
    ActorState,
    ConcreteScenario,
    CriticalityMetrics,
    Difficulty,
)


@dataclass
class Body:
    id: str
    actor_type: str
    x: float
    y: float
    vx: float
    vy: float
    heading_deg: float
    length: float
    width: float
    height: float
    behavior: str
    trigger_t: float | None = None
    lateral_speed: float | None = None
    target_y: float | None = None
    triggered: bool = False
    braking: bool = False
    decel: float = 0.0


@dataclass
class SimResult:
    metrics: CriticalityMetrics
    difficulty: Difficulty
    frames: list[dict] = field(default_factory=list)


def _speed(vx: float, vy: float) -> float:
    return math.hypot(vx, vy)


def _obb_overlap(a: Body, b: Body) -> bool:
    """Axis-aligned approximation (good enough for criticality)."""
    return (
        abs(a.x - b.x) < (a.length + b.length) * 0.5
        and abs(a.y - b.y) < (a.width + b.width) * 0.5
    )


def _signed_clearance(a: Body, b: Body) -> float:
    """Distance between two bounding boxes; negative once they overlap.

    Centre-to-centre distance cannot express "how close was the near miss"
    because it never crosses zero, so it is useless as a search objective.  This
    is signed and continuous through contact, which is what lets a criticality
    search bisect on the point where a collision starts.
    """
    gap_x = abs(a.x - b.x) - (a.length + b.length) * 0.5
    gap_y = abs(a.y - b.y) - (a.width + b.width) * 0.5
    if gap_x >= 0.0 or gap_y >= 0.0:
        # Separated on at least one axis: true clearance.
        return math.hypot(max(gap_x, 0.0), max(gap_y, 0.0))
    # Overlapping on both axes: penetration depth, as a negative number.
    return max(gap_x, gap_y)


def _ttc(ego: Body, other: Body) -> float | None:
    """Simple longitudinal TTC when closing."""
    dx = other.x - ego.x
    rel_vx = ego.vx - other.vx
    if rel_vx <= 0.1:
        return None
    # Account for half-lengths
    gap = dx - 0.5 * (ego.length + other.length)
    if gap <= 0:
        return 0.0
    return gap / rel_vx


def _required_decel(ego: Body, other: Body) -> float | None:
    ttc = _ttc(ego, other)
    if ttc is None or ttc <= 0:
        if ttc == 0.0:
            return 99.0
        return None
    # a = v_rel / ttc to stop relative closing
    rel = max(0.0, ego.vx - other.vx)
    if ttc < 1e-3:
        return 99.0
    return rel / ttc


def _apply_behavior(body: Body, t: float, dt: float, odd: dict) -> None:
    if body.behavior == "static":
        body.vx = body.vy = 0.0
        return

    if body.trigger_t is not None and t >= body.trigger_t:
        body.triggered = True

    if body.behavior == "brake" and body.triggered:
        decel = float(odd.get("lead_decel_mps2", 6.0))
        body.decel = decel
        body.vx = max(0.0, body.vx - decel * dt)
        body.vy = 0.0
        return

    if body.behavior == "accelerate" and body.triggered:
        accel = float(odd.get("lead_accel_mps2", 2.0))
        body.vx += accel * dt
        body.vy = 0.0
        return

    if body.behavior in ("cut_in", "cut_out", "swerve") and body.triggered:
        if body.target_y is not None and body.lateral_speed:
            dy = body.target_y - body.y
            step = body.lateral_speed * dt
            if abs(dy) <= step:
                body.y = body.target_y
                body.vy = 0.0
            else:
                body.vy = body.lateral_speed if dy > 0 else -body.lateral_speed
        return

    # constant_velocity / cross / encroach / left_turn: integrate as-is
    return


def simulate(
    scenario: ConcreteScenario,
    *,
    record_frames: bool = False,
    frame_stride: int = 1,
    reference_driver: ReferenceDriver | None = None,
) -> SimResult:
    """Run the scenario with the ego driven by the reference driver.

    ``reference_driver`` lets a criticality search vary the yardstick (a slower
    reaction, a lower braking bound) without touching the scenario itself.
    """
    dt = scenario.timestep_s
    n_steps = int(round(scenario.duration_s / dt))

    ego = Body(
        id=scenario.ego.id,
        actor_type=scenario.ego.actor_type,
        x=scenario.ego.x,
        y=scenario.ego.y,
        vx=scenario.ego.vx,
        vy=scenario.ego.vy,
        heading_deg=scenario.ego.heading_deg,
        length=scenario.ego.length_m,
        width=scenario.ego.width_m,
        height=scenario.ego.height_m,
        behavior=scenario.ego.behavior,
    )
    others = [
        Body(
            id=a.id,
            actor_type=a.actor_type,
            x=a.x,
            y=a.y,
            vx=a.vx,
            vy=a.vy,
            heading_deg=a.heading_deg,
            length=a.length_m,
            width=a.width_m,
            height=a.height_m,
            behavior=a.behavior,
            trigger_t=a.trigger_t,
            lateral_speed=a.lateral_speed,
            target_y=a.target_y,
        )
        for a in scenario.actors
    ]

    min_ttc: float | None = None
    min_dist: float | None = None
    min_clearance: float | None = None
    max_req_decel: float | None = None
    collision = False
    pet: float | None = None
    ego_entered_conflict = False
    other_left_conflict_t: float | None = None

    driver = reference_driver or ReferenceDriver.from_odd(scenario.odd)
    #: When each hazard first became perceptible to the reference driver.
    hazard_seen_at: dict[str, float | None] = {}

    frames: list[dict] = []

    for step in range(n_steps + 1):
        t = round(step * dt, 10)

        for body in others:
            _apply_behavior(body, t, dt, scenario.odd)

        # The ego is driven by the SUT-neutral reference driver: it notices a
        # hazard when TTC drops below the perception threshold, waits its risk
        # perception plus reaction time *from that moment*, then brakes.
        if step > 0:
            for body in others:
                ttc_now = _ttc(ego, body)
                if driver.perceives(ttc_now) and hazard_seen_at.get(body.id) is None:
                    hazard_seen_at[body.id] = t
                if driver.brakes_at(hazard_seen_at.get(body.id), t):
                    ego.vx = max(0.0, ego.vx - driver.max_decel_mps2 * dt)

        # Integrate
        if step > 0:
            ego.x += ego.vx * dt
            ego.y += ego.vy * dt
            for body in others:
                body.x += body.vx * dt
                body.y += body.vy * dt
                if body.vx or body.vy:
                    body.heading_deg = math.degrees(math.atan2(body.vy, body.vx))

        for body in others:
            dist = math.hypot(body.x - ego.x, body.y - ego.y)
            min_dist = dist if min_dist is None else min(min_dist, dist)

            clearance = _signed_clearance(ego, body)
            min_clearance = (
                clearance if min_clearance is None else min(min_clearance, clearance)
            )

            ttc = _ttc(ego, body)
            if ttc is not None:
                min_ttc = ttc if min_ttc is None else min(min_ttc, ttc)

            req = _required_decel(ego, body)
            if req is not None:
                max_req_decel = req if max_req_decel is None else max(max_req_decel, req)

            if _obb_overlap(ego, body):
                collision = True

            # Crude PET: time between ego reaching other's longitudinal position
            # and other clearing lateral corridor
            if abs(body.y) < 2.0 and body.x > ego.x - 2:
                ego_entered_conflict = True
            if ego_entered_conflict and abs(body.y) > 2.5 and other_left_conflict_t is None:
                other_left_conflict_t = t

        if record_frames and step % frame_stride == 0:
            frames.append(
                {
                    "t": t,
                    "ego": {"x": ego.x, "y": ego.y, "vx": ego.vx, "vy": ego.vy, "heading_deg": ego.heading_deg},
                    "actors": [
                        {
                            "id": b.id,
                            "actor_type": b.actor_type,
                            "x": b.x,
                            "y": b.y,
                            "vx": b.vx,
                            "vy": b.vy,
                            "heading_deg": b.heading_deg,
                            "length": b.length,
                            "width": b.width,
                            "height": b.height,
                        }
                        for b in others
                    ],
                }
            )

    if other_left_conflict_t is not None:
        pet = other_left_conflict_t

    # R157-style preventability using competent driver model
    # risk_perception=0.4s, reaction=0.75s, comfort max decel ~6 m/s^2, max ~9
    delay = driver.total_delay_s
    preventable: bool | None = None
    if min_ttc is not None:
        # If TTC after delay still allows stopping with 7 m/s^2
        t_remain = min_ttc - delay
        if t_remain <= 0:
            preventable = False
        elif max_req_decel is not None:
            # After delay, required decel increases
            preventable = max_req_decel < driver.max_decel_mps2 and t_remain > 0.3
        else:
            preventable = t_remain > 1.0
    elif collision:
        preventable = False
    else:
        preventable = True

    metrics = CriticalityMetrics(
        min_ttc_s=min_ttc,
        min_distance_m=min_dist,
        min_clearance_m=min_clearance,
        pet_s=pet,
        required_decel_mps2=max_req_decel,
        collision=collision,
        preventable=preventable,
    )

    # Difficulty tiers from R157-style preventability + TTC
    if preventable is False and (min_ttc is None or min_ttc < 1.0):
        difficulty = Difficulty.UNPREVENTABLE
    elif collision or (min_ttc is not None and min_ttc < 1.5) or (
        max_req_decel is not None and max_req_decel > 6.0
    ):
        difficulty = Difficulty.HARD
    elif (min_ttc is not None and min_ttc < 3.0) or (
        max_req_decel is not None and max_req_decel > 3.0
    ):
        difficulty = Difficulty.MEDIUM
    else:
        difficulty = Difficulty.EASY

    return SimResult(metrics=metrics, difficulty=difficulty, frames=frames)


def annotate_scenario(scenario: ConcreteScenario) -> ConcreteScenario:
    result = simulate(scenario, record_frames=False)
    scenario.metrics = result.metrics
    scenario.difficulty = result.difficulty
    return scenario
