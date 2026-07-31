"""Collision and geometry helpers (axis-aligned / oriented boxes)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OBB:
    """Oriented bounding box in 2D."""

    x: float
    y: float
    length: float
    width: float
    heading_rad: float

    def corners(self) -> list[tuple[float, float]]:
        hx = self.length / 2.0
        hy = self.width / 2.0
        c = math.cos(self.heading_rad)
        s = math.sin(self.heading_rad)
        local = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        return [
            (self.x + lx * c - ly * s, self.y + lx * s + ly * c) for lx, ly in local
        ]


def _project(axis: tuple[float, float], corners: list[tuple[float, float]]) -> tuple[float, float]:
    ax, ay = axis
    dots = [cx * ax + cy * ay for cx, cy in corners]
    return min(dots), max(dots)


def _overlap_1d(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def boxes_overlap(a: OBB, b: OBB, eps: float = 1e-9) -> bool:
    """Separating-axis theorem for two OBBs."""
    ca = a.corners()
    cb = b.corners()
    axes: list[tuple[float, float]] = []
    for box in (a, b):
        c = math.cos(box.heading_rad)
        s = math.sin(box.heading_rad)
        axes.append((c, s))
        axes.append((-s, c))
    for ax, ay in axes:
        norm = math.hypot(ax, ay)
        if norm < eps:
            continue
        axis = (ax / norm, ay / norm)
        pa = _project(axis, ca)
        pb = _project(axis, cb)
        if not _overlap_1d(pa, pb):
            return False
    return True


def point_in_aabb(
    px: float,
    py: float,
    cx: float,
    cy: float,
    half: float,
) -> bool:
    return abs(px - cx) <= half and abs(py - cy) <= half
