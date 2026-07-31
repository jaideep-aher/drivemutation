"""NumPy lidar raycaster over box/cylinder/plane primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from backend.app.signalforge.schema import Box3D

# Semantic labels
SEM_GROUND = 0
SEM_VEHICLE = 1
SEM_PEDESTRIAN = 2
SEM_CYCLIST = 3
SEM_ANIMAL = 4
SEM_STATIC = 5

TYPE_TO_SEM = {
    "vehicle": SEM_VEHICLE,
    "pedestrian": SEM_PEDESTRIAN,
    "cyclist": SEM_CYCLIST,
    "animal": SEM_ANIMAL,
    "static": SEM_STATIC,
    "ego": SEM_VEHICLE,
}


@dataclass
class Primitive:
    kind: str  # box | cylinder | plane
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    heading_deg: float
    semantic: int
    instance_id: int
    vx: float = 0.0
    vy: float = 0.0


def _heading_rad(deg: float) -> float:
    return math.radians(deg)


def actors_to_primitives(ego: dict, actors: list[dict], include_ego: bool = False) -> list[Primitive]:
    prims: list[Primitive] = [
        Primitive(
            kind="plane",
            x=0,
            y=0,
            z=0,
            length=200,
            width=200,
            height=0,
            heading_deg=0,
            semantic=SEM_GROUND,
            instance_id=0,
        )
    ]
    inst = 1
    if include_ego:
        prims.append(
            Primitive(
                kind="box",
                x=ego["x"],
                y=ego["y"],
                z=ego.get("z", 0.75),
                length=ego.get("length", 4.5),
                width=ego.get("width", 1.9),
                height=ego.get("height", 1.5),
                heading_deg=ego.get("heading_deg", 0),
                semantic=SEM_VEHICLE,
                instance_id=inst,
                vx=ego.get("vx", 0),
                vy=ego.get("vy", 0),
            )
        )
        inst += 1

    for a in actors:
        atype = a.get("actor_type", "vehicle")
        kind = "cylinder" if atype in ("pedestrian", "animal") else "box"
        h = a.get("height", 1.5)
        prims.append(
            Primitive(
                kind=kind,
                x=a["x"],
                y=a["y"],
                z=h * 0.5,
                length=a.get("length", 4.5),
                width=a.get("width", 1.8),
                height=h,
                heading_deg=a.get("heading_deg", 0),
                semantic=TYPE_TO_SEM.get(atype, SEM_STATIC),
                instance_id=inst,
                vx=a.get("vx", 0),
                vy=a.get("vy", 0),
            )
        )
        inst += 1
    return prims


def _ray_plane_z(ox, oy, oz, dx, dy, dz, z0=0.0):
    """Intersect rays with horizontal plane z=z0. Returns t or inf."""
    t = np.full(ox.shape, np.inf, dtype=np.float64)
    mask = np.abs(dz) > 1e-8
    t_cand = (z0 - oz[mask]) / dz[mask]
    valid = t_cand > 0.05
    t[np.where(mask)[0][valid]] = t_cand[valid]
    return t


def _ray_aabb(ox, oy, oz, dx, dy, dz, xmin, xmax, ymin, ymax, zmin, zmax):
    """Ray-AABB slab method; returns t_hit (inf if miss)."""
    n = ox.shape[0]
    tmin = np.zeros(n, dtype=np.float64)
    tmax = np.full(n, np.inf, dtype=np.float64)

    for o, d, bmin, bmax in (
        (ox, dx, xmin, xmax),
        (oy, dy, ymin, ymax),
        (oz, dz, zmin, zmax),
    ):
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = 1.0 / d
        t1 = (bmin - o) * inv
        t2 = (bmax - o) * inv
        t_near = np.minimum(t1, t2)
        t_far = np.maximum(t1, t2)
        # Parallel miss
        parallel = np.abs(d) < 1e-12
        outside = parallel & ((o < bmin) | (o > bmax))
        tmin = np.maximum(tmin, t_near)
        tmax = np.minimum(tmax, t_far)
        tmin = np.where(outside, np.inf, tmin)
        tmax = np.where(outside, -np.inf, tmax)

    hit = (tmax >= tmin) & (tmax > 0.05)
    t = np.where(hit, np.maximum(tmin, 0.05), np.inf)
    return t


def _transform_to_box_frame(ox, oy, px, py, heading_deg):
    """Translate/rotate points into box-local frame (axis-aligned)."""
    rad = math.radians(heading_deg)
    c, s = math.cos(-rad), math.sin(-rad)
    tx = ox - px
    ty = oy - py
    lx = c * tx - s * ty
    ly = s * tx + c * ty
    return lx, ly


def cast_lidar(
    primitives: list[Primitive],
    *,
    sensor_x: float = 0.0,
    sensor_y: float = 0.0,
    sensor_z: float = 1.8,
    n_beams: int = 32,
    n_azimuth: int = 256,
    fov_up_deg: float = 10.0,
    fov_down_deg: float = -30.0,
    max_range: float = 80.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Cast lidar rays from sensor pose.
    Returns xyz (N,3), intensity (N,), semantic (N,), instance (N,).
    """
    elev = np.linspace(math.radians(fov_down_deg), math.radians(fov_up_deg), n_beams)
    azim = np.linspace(0, 2 * math.pi, n_azimuth, endpoint=False)
    el, az = np.meshgrid(elev, azim, indexing="ij")
    el = el.ravel()
    az = az.ravel()

    dx = np.cos(el) * np.cos(az)
    dy = np.cos(el) * np.sin(az)
    dz = np.sin(el)

    n = dx.shape[0]
    ox = np.full(n, sensor_x, dtype=np.float64)
    oy = np.full(n, sensor_y, dtype=np.float64)
    oz = np.full(n, sensor_z, dtype=np.float64)

    best_t = np.full(n, np.inf)
    best_sem = np.zeros(n, dtype=np.int32)
    best_inst = np.zeros(n, dtype=np.int32)
    best_intensity = np.zeros(n, dtype=np.float64)

    for p in primitives:
        if p.kind == "plane":
            t = _ray_plane_z(ox, oy, oz, dx, dy, dz, z0=0.0)
            # Limit ground extent; compute hits only for finite t
            finite = np.isfinite(t)
            hit_x = np.zeros_like(t)
            hit_y = np.zeros_like(t)
            hit_x[finite] = ox[finite] + t[finite] * dx[finite]
            hit_y[finite] = oy[finite] + t[finite] * dy[finite]
            in_bounds = finite & (np.abs(hit_x - sensor_x) < 100) & (np.abs(hit_y - sensor_y) < 40)
            t = np.where(in_bounds, t, np.inf)
            intensity = 0.15 * np.ones(n)
        elif p.kind == "cylinder":
            # Approximate cylinder as AABB in world (good enough for demo)
            r = max(p.width, p.length) * 0.5
            t = _ray_aabb(
                ox, oy, oz, dx, dy, dz,
                p.x - r, p.x + r,
                p.y - r, p.y + r,
                0.0, p.height,
            )
            intensity = 0.55 * np.ones(n)
        else:
            # Box: transform rays into box frame for AABB
            rad = math.radians(p.heading_deg)
            c, s = math.cos(-rad), math.sin(-rad)
            # Origin relative
            rx = ox - p.x
            ry = oy - p.y
            lx = c * rx - s * ry
            ly = s * rx + c * ry
            lz = oz
            ldx = c * dx - s * dy
            ldy = s * dx + c * dy
            ldz = dz
            hl, hw, hh = p.length * 0.5, p.width * 0.5, p.height * 0.5
            t = _ray_aabb(lx, ly, lz, ldx, ldy, ldz, -hl, hl, -hw, hw, -hh + p.z, hh + (p.z - hh))
            # Fix z: box centered at z=height/2
            t = _ray_aabb(
                lx, ly, oz, ldx, ldy, dz,
                -hl, hl, -hw, hw, 0.0, p.height,
            )
            intensity = 0.7 * np.ones(n)

        better = t < best_t
        best_t = np.where(better, t, best_t)
        best_sem = np.where(better, p.semantic, best_sem)
        best_inst = np.where(better, p.instance_id, best_inst)
        best_intensity = np.where(better, intensity, best_intensity)

    valid = (best_t < max_range) & np.isfinite(best_t)
    px = ox[valid] + best_t[valid] * dx[valid]
    py = oy[valid] + best_t[valid] * dy[valid]
    pz = oz[valid] + best_t[valid] * dz[valid]
    # Range attenuation on intensity
    rng = best_t[valid]
    inten = best_intensity[valid] * np.clip(1.0 - rng / max_range, 0.05, 1.0)

    xyz = np.stack([px, py, pz], axis=1)
    return xyz, inten, best_sem[valid], best_inst[valid]


def primitives_to_boxes(primitives: list[Primitive], hits_per_inst: dict[int, int] | None = None) -> list[Box3D]:
    boxes: list[Box3D] = []
    hits_per_inst = hits_per_inst or {}
    for p in primitives:
        if p.kind == "plane" or p.instance_id == 0:
            continue
        n_hits = hits_per_inst.get(p.instance_id, 0)
        # Occlusion proxy: fewer hits => more occluded
        if n_hits <= 0:
            occ = 1.0
        elif n_hits < 10:
            occ = 0.75
        elif n_hits < 40:
            occ = 0.4
        elif n_hits < 100:
            occ = 0.15
        else:
            occ = 0.0
        cat = {
            SEM_VEHICLE: "vehicle",
            SEM_PEDESTRIAN: "pedestrian",
            SEM_CYCLIST: "cyclist",
            SEM_ANIMAL: "animal",
            SEM_STATIC: "static",
        }.get(p.semantic, "static")
        boxes.append(
            Box3D(
                instance_id=p.instance_id,
                category=cat,
                x=p.x,
                y=p.y,
                z=p.height * 0.5,
                length=p.length,
                width=p.width,
                height=p.height,
                heading_deg=p.heading_deg,
                vx=p.vx,
                vy=p.vy,
                occlusion=occ,
                num_lidar_hits=n_hits,
            )
        )
    return boxes
