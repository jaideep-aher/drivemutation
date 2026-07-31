"""Combinatorial ODD expansion from logical to concrete scenarios."""

from __future__ import annotations

import itertools
import math
import random
from typing import Any, Iterator

from backend.app.signalforge.constraints import is_feasible
from backend.app.signalforge.schema import (
    ActorState,
    ConcreteScenario,
    Lighting,
    LogicalScenario,
    Provenance,
    RoadGeometry,
    Weather,
)


def _kph_to_mps(kph: float) -> float:
    return kph / 3.6


def _sample_range(lo: float, hi: float, rng: random.Random) -> float:
    if hi <= lo:
        return lo
    return rng.uniform(lo, hi)


def _pick(values: list[Any], rng: random.Random) -> Any:
    return values[rng.randrange(len(values))]


def _actor_layout(
    logical: LogicalScenario,
    ego_speed_kph: float,
    actor_speed_kph: float,
    distance_m: float,
    odd: dict[str, Any],
    rng: random.Random,
) -> tuple[ActorState, list[ActorState]]:
    ego_v = _kph_to_mps(ego_speed_kph)
    ego = ActorState(
        id="ego",
        actor_type="vehicle",
        x=0.0,
        y=0.0,
        z=0.0,
        vx=ego_v,
        vy=0.0,
        heading_deg=0.0,
        length_m=4.5,
        width_m=1.9,
        height_m=1.5,
        behavior="constant_velocity",
    )

    actors: list[ActorState] = []
    family = logical.family.value

    for i, spec in enumerate(logical.actors):
        aid = f"{spec.role}_{i}"
        av = _kph_to_mps(actor_speed_kph if spec.actor_type != "static" else 0.0)
        x, y = distance_m, 0.0
        vx, vy = av, 0.0
        heading = 0.0
        trigger_t = None
        post_vx = post_vy = None
        lateral_speed = None
        target_y = None
        behavior = spec.behavior

        if family in ("rear_end", "deceleration") or spec.behavior == "brake":
            x, y = distance_m, 0.0
            vx, vy = av, 0.0
            trigger_t = 1.0 + rng.uniform(0, 1.5)
            decel = float(odd.get("lead_decel_mps2", 6.0))
            post_vx = max(0.0, av - decel)  # will be applied as continuous brake in sim
            behavior = "brake"
            # Encode decel in odd for sim
            odd.setdefault("lead_decel_mps2", decel)

        elif family in ("cut_in", "lane_change") or spec.behavior == "cut_in":
            lane_offset = 3.5 if rng.random() > 0.5 else -3.5
            x = distance_m * (0.3 + 0.5 * rng.random())
            y = lane_offset
            vx = av
            trigger_t = 0.5 + rng.uniform(0, 1.5)
            lateral_speed = 1.2 + rng.uniform(0, 1.0)
            target_y = 0.0
            behavior = "cut_in"

        elif family == "cut_out" or spec.behavior == "cut_out":
            if spec.role == "obstacle" or spec.actor_type == "static":
                x, y = distance_m + 15.0, 0.0
                vx = vy = 0.0
                behavior = "static"
            else:
                x, y = distance_m, 0.0
                vx = av
                trigger_t = 1.0 + rng.uniform(0, 1.0)
                lateral_speed = 1.5
                target_y = 3.5 if rng.random() > 0.5 else -3.5
                behavior = "cut_out"

        elif family in ("pedestrian", "pedalcyclist", "vru_crossing", "animal") or spec.behavior == "cross":
            approach = odd.get("approach", "nearside")
            side = 1.0 if approach != "farside" else -1.0
            if "impact_offset_pct" in odd:
                offset_frac = float(odd["impact_offset_pct"]) / 100.0 - 0.5
            else:
                offset_frac = rng.uniform(-0.3, 0.3)
            # Position so they reach ego path near collision geometry
            x = distance_m
            y = side * (4.0 + rng.uniform(0, 3.0))
            vx = 0.0
            vy = -side * max(av, 0.5)
            heading = 90.0 if vy < 0 else -90.0
            behavior = "cross"
            # Parked occluder
            if spec.role in ("parked",) or (spec.actor_type == "vehicle" and behavior == "static"):
                x = distance_m - 2.0
                y = side * 2.5
                vx = vy = 0.0
                heading = 0.0
                behavior = "static"

        elif family == "crossing_paths" or spec.behavior == "left_turn":
            x, y = distance_m, -distance_m * 0.3
            vx = av * 0.7
            vy = av * 0.5
            heading = 45.0
            behavior = "left_turn"

        elif family == "opposite_direction" or spec.behavior == "encroach":
            encroach = float(odd.get("encroach_m", 1.0))
            x = distance_m
            y = -3.5 + encroach  # oncoming lane encroaching
            vx = -av
            vy = 0.0
            heading = 180.0
            behavior = "encroach"

        elif family == "control_loss" or spec.behavior == "swerve":
            x = distance_m
            y = 3.5
            vx = av
            trigger_t = 0.8
            lateral_speed = 2.0 + rng.uniform(0, 1.5)
            target_y = 0.0
            behavior = "swerve"

        elif family == "road_departure":
            x = distance_m
            y = -2.0 - rng.uniform(0, 2.0)
            vx = vy = 0.0
            behavior = "static"

        else:
            x = distance_m
            y = rng.uniform(-2, 2)
            vx = av if spec.actor_type != "static" else 0.0

        # Occlusion parked car helper for hazop ped
        if spec.role == "parked":
            x = max(5.0, distance_m - 3.0)
            y = 2.8
            vx = vy = 0.0
            behavior = "static"

        if family == "opposite_direction" and "wrong" in (spec.role or ""):
            x = distance_m
            y = 0.0
            vx = -av
            heading = 180.0

        actors.append(
            ActorState(
                id=aid,
                actor_type=spec.actor_type,
                x=x,
                y=y,
                z=0.0,
                vx=vx,
                vy=vy,
                heading_deg=heading,
                length_m=spec.length_m,
                width_m=spec.width_m,
                height_m=spec.height_m,
                behavior=behavior,
                trigger_t=trigger_t,
                post_vx=post_vx,
                post_vy=post_vy,
                lateral_speed=lateral_speed,
                target_y=target_y,
            )
        )

    return ego, actors


def _odd_combos(logical: LogicalScenario, max_combos: int = 96) -> list[dict[str, Any]]:
    """Build limited combinatorial ODD parameter sets."""
    keys = sorted(logical.odd_params.keys())
    if not keys:
        return [{}]
    value_lists = [logical.odd_params[k] for k in keys]
    combos = []
    for values in itertools.product(*value_lists):
        combos.append(dict(zip(keys, values)))
        if len(combos) >= max_combos:
            break
    return combos


def expand_logical(
    logical: LogicalScenario,
    *,
    samples_per_combo: int = 2,
    seed: int = 0,
    max_per_logical: int = 200,
) -> list[ConcreteScenario]:
    """Expand one logical scenario into many concrete variants."""
    rng = random.Random(seed)
    results: list[ConcreteScenario] = []
    odd_combos = _odd_combos(logical)

    # Cover weather x lighting x road with sampling
    env_combos = list(
        itertools.product(logical.weathers, logical.lightings, logical.road_geometries)
    )
    rng.shuffle(env_combos)

    idx = 0
    for weather, lighting, road in env_combos:
        for odd_base in odd_combos:
            for _ in range(samples_per_combo):
                if len(results) >= max_per_logical:
                    return results
                local_seed = seed + idx * 9973
                local_rng = random.Random(local_seed)
                odd = dict(odd_base)

                ego_spd = _sample_range(logical.ego_speed_kph.min, logical.ego_speed_kph.max, local_rng)
                act_spd = _sample_range(
                    logical.actor_speed_kph.min, logical.actor_speed_kph.max, local_rng
                )
                dist = _sample_range(logical.distance_m.min, logical.distance_m.max, local_rng)

                # Sync TTC-ish for rear-end families — keep a safer minimum gap
                if logical.ttc_s is not None and logical.family.value in (
                    "rear_end",
                    "deceleration",
                    "cut_in",
                ):
                    ttc = _sample_range(logical.ttc_s.min, logical.ttc_s.max, local_rng)
                    rel = max(1.0, _kph_to_mps(ego_spd) - _kph_to_mps(act_spd))
                    dist = max(
                        max(logical.distance_m.min, 12.0),
                        min(logical.distance_m.max, ttc * rel + 6.0),
                    )
                else:
                    dist = max(dist, 10.0)

                ego, actors = _actor_layout(logical, ego_spd, act_spd, dist, odd, local_rng)

                # Sensor degradation defaults from weather
                if weather == Weather.RAIN:
                    odd.setdefault("lidar_dropout", 0.15 + 0.2 * local_rng.random())
                    odd.setdefault("rain_intensity", 0.4 + 0.5 * local_rng.random())
                if lighting in (Lighting.DUSK, Lighting.DAWN):
                    odd.setdefault("camera_glare", local_rng.random() > 0.5)

                concrete = ConcreteScenario(
                    id=f"{logical.id}__{idx:04d}",
                    logical_id=logical.id,
                    family=logical.family,
                    name=f"{logical.name} [{weather.value}/{lighting.value}/{road.value}]",
                    provenance=Provenance(
                        source=logical.provenance.source,
                        citation=logical.provenance.citation,
                        parent_id=logical.id,
                        seed=local_seed,
                        notes=logical.provenance.notes,
                    ),
                    weather=weather,
                    lighting=lighting,
                    road_geometry=road,
                    duration_s=8.0,
                    timestep_s=0.1,
                    ego=ego,
                    actors=actors,
                    odd=odd,
                    crash_frequency_weight=logical.crash_frequency_weight,
                )

                if is_feasible(concrete):
                    results.append(concrete)
                    idx += 1
                else:
                    idx += 1  # still advance id space

    return results


def expand_catalog(
    logicals: list[LogicalScenario],
    *,
    target_count: int = 2500,
    seed: int = 42,
) -> list[ConcreteScenario]:
    """Expand full catalog aiming for target_count concrete scenarios."""
    if not logicals:
        return []
    per = max(80, math.ceil(target_count / len(logicals)) + 40)
    all_concrete: list[ConcreteScenario] = []
    for i, logical in enumerate(logicals):
        batch = expand_logical(
            logical,
            samples_per_combo=4,
            seed=seed + i * 10007,
            max_per_logical=per,
        )
        all_concrete.extend(batch)

    # If still short, keep sampling high-weight logicals with fresh seeds
    extra_seed = seed + 99991
    guard = 0
    while len(all_concrete) < target_count and guard < 20:
        guard += 1
        ranked = sorted(logicals, key=lambda s: -s.crash_frequency_weight)
        for i, logical in enumerate(ranked):
            if len(all_concrete) >= target_count:
                break
            need = target_count - len(all_concrete)
            batch = expand_logical(
                logical,
                samples_per_combo=3,
                seed=extra_seed + guard * 1000 + i,
                max_per_logical=min(need + 10, 120),
            )
            # Deduplicate by provenance seed + weather + lighting
            existing = {s.id for s in all_concrete}
            for s in batch:
                # Remap id to avoid collisions
                s.id = f"{logical.id}__x{guard}_{len(all_concrete):04d}"
                if s.id not in existing:
                    all_concrete.append(s)
                    existing.add(s.id)
                if len(all_concrete) >= target_count:
                    break

    if len(all_concrete) > target_count:
        all_concrete.sort(key=lambda s: -s.crash_frequency_weight)
        all_concrete = all_concrete[:target_count]
    return all_concrete
