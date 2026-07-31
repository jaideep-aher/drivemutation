"""TTC and kinematic metric helpers."""

from __future__ import annotations

import math


def speed(vx: float, vy: float) -> float:
    return math.hypot(vx, vy)


def relative_ttc(
    x1: float,
    y1: float,
    vx1: float,
    vy1: float,
    x2: float,
    y2: float,
    vx2: float,
    vy2: float,
    combine_radius: float,
) -> float | None:
    """Approximate time-to-collision using closing relative velocity.

    Returns None if not closing or already overlapping beyond radius model.
    Uses point-mass centres with combined radius for Stage-1 determinism.
    """
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    if dist <= combine_radius:
        return 0.0
    rvx = vx1 - vx2
    rvy = vy1 - vy2
    # Component of relative velocity along line connecting centres (positive = closing)
    closing = (dx * rvx + dy * rvy) / dist
    if closing <= 1e-9:
        return None
    gap = dist - combine_radius
    return gap / closing


def finite_diff(prev: float, curr: float, dt: float) -> float:
    if dt <= 0:
        return 0.0
    return (curr - prev) / dt
