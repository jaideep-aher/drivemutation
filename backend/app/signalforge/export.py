"""nuScenes-inspired JSON export with provenance table."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.signalforge.render import render_scenario
from backend.app.signalforge.schema import ConcreteScenario, PointCloudFrame


def export_scenario_bundle(
    scenario: ConcreteScenario,
    frames: list[PointCloudFrame] | None = None,
    *,
    max_frames: int = 12,
) -> dict:
    """Build a compact nuScenes-inspired bundle for one scenario."""
    if frames is None:
        frames = render_scenario(scenario, max_frames=max_frames, lidar_beams=24, lidar_azimuth=160)

    sample_data = []
    annotations = []
    for i, fr in enumerate(frames):
        sample_token = f"{scenario.id}_s{i}"
        sample_data.append(
            {
                "token": sample_token,
                "timestamp": int(fr.t * 1e6),
                "filename_lidar": f"samples/LIDAR_TOP/{sample_token}.bin",
                "filename_radar": f"samples/RADAR_FRONT/{sample_token}.pcd",
                "num_lidar_pts": len(fr.xyz) // 3,
                "num_radar_pts": len(fr.radar_xyz) // 3,
                "ego_pose_token": f"{scenario.id}_pose{i}",
            }
        )
        for box in fr.boxes:
            annotations.append(
                {
                    "sample_token": sample_token,
                    "instance_id": box.instance_id,
                    "category": box.category,
                    "translation": [box.x, box.y, box.z],
                    "size": [box.width, box.length, box.height],
                    "rotation_yaw_deg": box.heading_deg,
                    "velocity": [box.vx, box.vy],
                    "visibility_occlusion": box.occlusion,
                    "num_lidar_pts": box.num_lidar_hits,
                }
            )

    return {
        "meta": {
            "format": "signalforge-nuscenes-lite",
            "version": "0.1.0",
        },
        "scene": {
            "token": scenario.id,
            "name": scenario.name,
            "family": scenario.family.value,
            "weather": scenario.weather.value,
            "lighting": scenario.lighting.value,
            "road_geometry": scenario.road_geometry.value,
            "difficulty": scenario.difficulty.value if scenario.difficulty else None,
            "nbr_samples": len(frames),
        },
        "provenance": scenario.provenance.model_dump(mode="json"),
        "metrics": scenario.metrics.model_dump(mode="json") if scenario.metrics else None,
        "calibrated_sensor": {
            "lidar_top": {"modality": "lidar", "beams": 24, "translation": [0, 0, 1.8]},
            "radar_front": {"modality": "radar", "fov_deg": 160, "translation": [0, 0, 0.5]},
        },
        "sample_data": sample_data,
        "sample_annotation": annotations,
        "frames": [f.model_dump(mode="json") for f in frames],
    }


def write_export(scenario: ConcreteScenario, out_path: Path, **kwargs) -> Path:
    bundle = export_scenario_bundle(scenario, **kwargs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle))
    return out_path
