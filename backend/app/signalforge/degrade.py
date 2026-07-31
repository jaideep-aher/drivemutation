"""Sensor degradation layer applied on top of clean returns."""

from __future__ import annotations

import numpy as np

from backend.app.signalforge.schema import Weather


def degrade_lidar(
    xyz: np.ndarray,
    intensity: np.ndarray,
    semantic: np.ndarray,
    instance: np.ndarray,
    *,
    weather: Weather | str = Weather.CLEAR,
    odd: dict | None = None,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Apply rain dropout, range attenuation, dirt occlusion, beam dropout."""
    if xyz.size == 0:
        return xyz, intensity, semantic, instance

    odd = odd or {}
    rng = np.random.default_rng(seed)
    weather_s = weather.value if hasattr(weather, "value") else str(weather)

    keep = np.ones(len(xyz), dtype=bool)
    inten = intensity.astype(np.float64).copy()

    # Rain: dropout + range attenuation
    rain = float(odd.get("rain_intensity", 0.0))
    if weather_s == "rain" or rain > 0:
        rain = max(rain, 0.4 if weather_s == "rain" else rain)
        dropout = float(odd.get("lidar_dropout", 0.1 + 0.4 * rain))
        ranges = np.linalg.norm(xyz[:, :2], axis=1)
        # Far points more likely to drop
        p_drop = dropout * np.clip(ranges / 60.0, 0.2, 1.0)
        keep &= rng.random(len(xyz)) > p_drop
        inten *= np.clip(1.0 - 0.5 * rain, 0.2, 1.0)

    # Fog: shorter effective range
    if weather_s == "fog":
        ranges = np.linalg.norm(xyz, axis=1)
        keep &= ranges < (25.0 + 15.0 * rng.random())
        inten *= 0.6

    # Snow
    if weather_s == "snow":
        dropout = float(odd.get("lidar_dropout", 0.25))
        keep &= rng.random(len(xyz)) > dropout
        # Fake near-field clutter
        n_clutter = int(0.02 * len(xyz))
        if n_clutter > 0 and keep.sum() > 10:
            clutter_idx = rng.choice(np.where(keep)[0], size=min(n_clutter, int(keep.sum())), replace=False)
            inten[clutter_idx] = rng.uniform(0.05, 0.2, size=len(clutter_idx))

    # Dirt occlusion: wipe a sector of azimuth
    dirt = float(odd.get("dirt_occlusion", 0.0))
    if dirt > 0:
        az = np.arctan2(xyz[:, 1], xyz[:, 0])
        sector = dirt * math_pi()
        keep &= ~((az > -sector * 0.5) & (az < sector * 0.5) & (xyz[:, 0] > 0))

    # Random beam dropout (entire elevation rings approximated by z bands)
    if float(odd.get("beam_dropout", 0.0)) > 0 or rng.random() < 0.15:
        z_band = rng.uniform(0.2, 1.5)
        keep &= np.abs(xyz[:, 2] - z_band) > 0.15

    return xyz[keep], inten[keep], semantic[keep], instance[keep]


def math_pi() -> float:
    return 3.141592653589793


def degrade_radar(
    xyz: np.ndarray,
    doppler: np.ndarray,
    rcs: np.ndarray,
    *,
    weather: Weather | str = Weather.CLEAR,
    odd: dict | None = None,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if xyz.size == 0:
        return xyz, doppler, rcs
    odd = odd or {}
    rng = np.random.default_rng(seed + 1)
    weather_s = weather.value if hasattr(weather, "value") else str(weather)
    keep = np.ones(len(xyz), dtype=bool)

    if weather_s in ("rain", "snow"):
        keep &= rng.random(len(xyz)) > 0.15
        # Multipath ghosts: duplicate some detections with offset
        pass

    # Multipath under "overpass" odd flag
    if odd.get("multipath") or weather_s == "rain":
        if len(xyz) > 0 and rng.random() < 0.3:
            ghost = xyz[0:1].copy()
            ghost[0, 1] += rng.uniform(-2, 2)
            xyz = np.vstack([xyz, ghost])
            doppler = np.concatenate([doppler, doppler[0:1] * 0.5])
            rcs = np.concatenate([rcs, rcs[0:1] * 0.3])
            keep = np.concatenate([keep, np.array([True])])

    return xyz[keep], doppler[keep], rcs[keep]
