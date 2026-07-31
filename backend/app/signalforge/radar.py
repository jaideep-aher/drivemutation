"""Radar returns: RCS model + Doppler from relative velocity."""

from __future__ import annotations

import math

import numpy as np

from backend.app.signalforge.lidar import Primitive


# Approximate RCS by class (m^2)
RCS = {
    1: 10.0,   # vehicle
    2: 0.5,    # pedestrian
    3: 1.0,    # cyclist
    4: 0.8,    # animal
    5: 5.0,    # static
}


def cast_radar(
    primitives: list[Primitive],
    *,
    sensor_x: float = 0.0,
    sensor_y: float = 0.0,
    sensor_z: float = 0.5,
    ego_vx: float = 0.0,
    ego_vy: float = 0.0,
    max_range: float = 100.0,
    fov_deg: float = 160.0,
    noise_std: float = 0.3,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    One detection per non-ground primitive in FOV.
    Returns xyz (M,3), doppler (M,), rcs (M,).
    """
    rng = rng or np.random.default_rng(0)
    half = math.radians(fov_deg * 0.5)
    xs, ys, zs, dops, rcs_vals = [], [], [], [], []

    for p in primitives:
        if p.kind == "plane" or p.instance_id == 0:
            continue
        dx = p.x - sensor_x
        dy = p.y - sensor_y
        dist = math.hypot(dx, dy)
        if dist < 0.5 or dist > max_range:
            continue
        bearing = math.atan2(dy, dx)
        if abs(bearing) > half:
            continue

        # Relative radial velocity (Doppler)
        rel_vx = p.vx - ego_vx
        rel_vy = p.vy - ego_vy
        if dist > 1e-6:
            radial = (rel_vx * dx + rel_vy * dy) / dist
        else:
            radial = 0.0

        rcs = RCS.get(p.semantic, 1.0)
        # Range-dependent SNR filter: drop weak far targets
        snr = rcs / (dist * dist + 1.0)
        if snr < 0.00005 and p.semantic not in (1, 5):
            continue

        noise = rng.normal(0, noise_std, size=3)
        xs.append(p.x + noise[0] * 0.2)
        ys.append(p.y + noise[1] * 0.2)
        zs.append(sensor_z + noise[2] * 0.1)
        dops.append(radial + float(rng.normal(0, 0.15)))
        rcs_vals.append(rcs)

    if not xs:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros(0, dtype=np.float64),
            np.zeros(0, dtype=np.float64),
        )
    xyz = np.stack([xs, ys, zs], axis=1)
    return xyz, np.asarray(dops), np.asarray(rcs_vals)
