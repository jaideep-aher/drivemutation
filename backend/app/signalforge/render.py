"""Render pipeline: simulate frames -> lidar/radar -> GT boxes."""

from __future__ import annotations

from collections import Counter

import numpy as np

from backend.app.signalforge.degrade import degrade_lidar, degrade_radar
from backend.app.signalforge.lidar import (
    actors_to_primitives,
    cast_lidar,
    primitives_to_boxes,
)
from backend.app.signalforge.radar import cast_radar
from backend.app.signalforge.schema import ConcreteScenario, PointCloudFrame
from backend.app.signalforge.sim import simulate


def render_scenario(
    scenario: ConcreteScenario,
    *,
    max_frames: int = 20,
    lidar_beams: int = 32,
    lidar_azimuth: int = 256,
    degrade: bool = True,
) -> list[PointCloudFrame]:
    """Simulate and render subsampled frames to point clouds."""
    # Determine stride so we get ~max_frames
    n_steps = int(round(scenario.duration_s / scenario.timestep_s))
    stride = max(1, n_steps // max(1, max_frames))
    result = simulate(scenario, record_frames=True, frame_stride=stride)
    frames_out: list[PointCloudFrame] = []

    seed_base = scenario.provenance.seed

    for fi, fr in enumerate(result.frames[:max_frames]):
        ego = {
            "x": fr["ego"]["x"],
            "y": fr["ego"]["y"],
            "vx": fr["ego"]["vx"],
            "vy": fr["ego"]["vy"],
            "heading_deg": fr["ego"]["heading_deg"],
            "length": scenario.ego.length_m,
            "width": scenario.ego.width_m,
            "height": scenario.ego.height_m,
        }
        # Transform actors into ego frame for ego-centric lidar
        actors_ego = []
        for a in fr["actors"]:
            # World to ego-ish: subtract ego position (heading~0 for demo)
            actors_ego.append(
                {
                    "id": a["id"],
                    "actor_type": a["actor_type"],
                    "x": a["x"] - ego["x"],
                    "y": a["y"] - ego["y"],
                    "vx": a["vx"],
                    "vy": a["vy"],
                    "heading_deg": a["heading_deg"],
                    "length": a["length"],
                    "width": a["width"],
                    "height": a["height"],
                }
            )

        prims = actors_to_primitives({"x": 0, "y": 0, "vx": ego["vx"], "vy": ego["vy"]}, actors_ego)
        xyz, inten, sem, inst = cast_lidar(
            prims,
            sensor_x=0.0,
            sensor_y=0.0,
            sensor_z=1.8,
            n_beams=lidar_beams,
            n_azimuth=lidar_azimuth,
        )

        if degrade:
            xyz, inten, sem, inst = degrade_lidar(
                xyz,
                inten,
                sem,
                inst,
                weather=scenario.weather,
                odd=scenario.odd,
                seed=seed_base + fi,
            )

        hit_counts = Counter(inst.tolist()) if len(inst) else Counter()
        boxes = primitives_to_boxes(prims, hits_per_inst=dict(hit_counts))

        r_xyz, r_dop, r_rcs = cast_radar(
            prims,
            sensor_x=0.0,
            sensor_y=0.0,
            ego_vx=ego["vx"],
            ego_vy=ego["vy"],
            rng=np.random.default_rng(seed_base + 1000 + fi),
        )
        if degrade:
            r_xyz, r_dop, r_rcs = degrade_radar(
                r_xyz,
                r_dop,
                r_rcs,
                weather=scenario.weather,
                odd=scenario.odd,
                seed=seed_base + 2000 + fi,
            )

        frames_out.append(
            PointCloudFrame(
                t=fr["t"],
                xyz=xyz.reshape(-1).tolist(),
                intensity=inten.tolist(),
                semantic=sem.tolist(),
                instance=inst.tolist(),
                boxes=boxes,
                radar_xyz=r_xyz.reshape(-1).tolist(),
                radar_doppler=r_dop.tolist(),
                radar_rcs=r_rcs.tolist(),
            )
        )

    return frames_out
