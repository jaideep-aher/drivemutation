"""Combinatorial ODD expansion from logical to concrete scenarios."""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Sequence

from backend.app.signalforge.constraints import is_feasible
from backend.app.signalforge.covering import CoverageReport, covering_array, coverage_of
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

        if family in ("rear_end", "deceleration") or spec.behavior in (
            "brake",
            "accelerate",
        ):
            # The rear-end group covers five distinct lead-vehicle behaviours in
            # the NHTSA typology — stopped, slower, accelerating, decelerating,
            # and a following vehicle manoeuvring — so dispatch on the declared
            # behaviour rather than forcing every one of them into a brake.
            x, y = distance_m, 0.0
            vy = 0.0
            if spec.behavior == "static":
                vx = 0.0
                behavior = "static"
            elif spec.behavior == "accelerate":
                vx = av
                trigger_t = 1.0 + rng.uniform(0, 1.0)
                behavior = "accelerate"
                odd.setdefault("lead_accel_mps2", 2.0)
            elif spec.behavior == "constant_velocity":
                vx = av
                behavior = "constant_velocity"
            else:
                vx = av
                trigger_t = 1.0 + rng.uniform(0, 1.5)
                decel = float(odd.get("lead_decel_mps2", 6.0))
                post_vx = max(0.0, av - decel)  # applied as continuous brake in sim
                behavior = "brake"
                odd.setdefault("lead_decel_mps2", decel)

        elif family in ("object", "evasive_action", "backing", "vehicle_failure"):
            # A hazard sitting in, or moving into, the ego's path.  Placed on the
            # lane centre rather than scattered laterally, because an object the
            # ego drives past is not the scenario the typology describes.
            x = distance_m
            y = rng.uniform(-0.6, 0.6)
            if spec.actor_type == "static" or spec.behavior == "static":
                vx = vy = 0.0
                behavior = "static"
            elif spec.behavior == "swerve":
                y = 3.5
                vx = av
                trigger_t = 0.8 + rng.uniform(0, 0.8)
                lateral_speed = 2.0 + rng.uniform(0, 1.5)
                target_y = 0.0
                behavior = "swerve"
            else:
                vx = av
                behavior = "constant_velocity"

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


#: Discrete ODD dimensions that always take part in the covering array, on top
#: of whatever ``odd_params`` a logical scenario declares.
ENV_DIMENSIONS = ("weather", "lighting", "road_geometry")


def odd_space(logical: LogicalScenario) -> dict[str, list[Any]]:
    """The full discrete ODD space of a logical scenario.

    Environment (weather, lighting, road geometry) and scenario-specific ODD
    parameters are deliberately treated as one space rather than nested loops,
    so the covering array can guarantee pairs *across* that boundary — rain with
    a 9 m/s2 lead deceleration, night with full occlusion — which nesting a
    truncated product inside a full one never did.
    """
    space: dict[str, list[Any]] = {
        "weather": list(logical.weathers),
        "lighting": list(logical.lightings),
        "road_geometry": list(logical.road_geometries),
    }
    for key, values in logical.odd_params.items():
        if values:
            space[key] = list(values)
    return space


def odd_forbidden(logical: LogicalScenario) -> Callable[[dict[str, Any]], bool]:
    """Constraints expressible on the discrete ODD alone.

    These mirror the physical checks in :mod:`constraints`, but applied *before*
    a scenario is built.  Rejecting after the fact loses coverage silently; the
    covering array instead treats these combinations as unreachable and says so.
    """

    def forbidden(row: dict[str, Any]) -> bool:
        # Ice does not form on a clear, dry road.
        if row.get("surface") == "ice" and row.get("weather") == Weather.CLEAR:
            return True
        # A lane change needs somewhere to change into.
        if logical.family.value == "lane_change":
            lanes = row.get("lane_count")
            if lanes is not None and int(lanes) < 2:
                return True
        return False

    return forbidden


def _odd_combos(logical: LogicalScenario, strength: int = 2, seed: int = 0) -> list[dict[str, Any]]:
    """Covering array over the discrete ODD space of one logical scenario."""
    rows, _ = covering_array(
        odd_space(logical),
        strength=strength,
        forbidden=odd_forbidden(logical),
        seed=seed,
    )
    return rows


def _build_concrete(
    logical: LogicalScenario,
    row: dict[str, Any],
    *,
    idx: int,
    local_seed: int,
) -> ConcreteScenario:
    """Instantiate one concrete scenario from a discrete ODD row plus a seed.

    The row fixes the discrete dimensions; the seed drives the continuous ones
    (speeds, distances, trigger times), so the same row can be instantiated many
    times without weakening the coverage guarantee.
    """
    local_rng = random.Random(local_seed)
    weather: Weather = row["weather"]
    lighting: Lighting = row["lighting"]
    road: RoadGeometry = row["road_geometry"]
    odd = {k: v for k, v in row.items() if k not in ENV_DIMENSIONS}

    ego_spd = _sample_range(logical.ego_speed_kph.min, logical.ego_speed_kph.max, local_rng)
    act_spd = _sample_range(logical.actor_speed_kph.min, logical.actor_speed_kph.max, local_rng)
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

    return ConcreteScenario(
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


def expand_logical(
    logical: LogicalScenario,
    *,
    samples_per_combo: int = 2,
    seed: int = 0,
    max_per_logical: int = 200,
    strength: int = 2,
) -> list[ConcreteScenario]:
    """Expand one logical scenario into many concrete variants.

    The discrete ODD backbone comes from a t-way covering array, so every pair of
    ODD values that is physically reachable appears in at least one variant.
    Continuous parameters are re-sampled on each pass over that backbone, which
    adds variety without diluting the guarantee.
    """
    rows = _odd_combos(logical, strength=strength, seed=seed)
    if not rows:
        return []

    results: list[ConcreteScenario] = []
    idx = 0

    for pass_i in range(max(1, samples_per_combo)):
        for row in rows:
            if len(results) >= max_per_logical:
                return results
            # A row can produce an infeasible layout for an unlucky draw of the
            # continuous parameters.  Retry the same row with fresh draws before
            # giving up, so a single bad sample does not punch a hole in the
            # coverage the array just guaranteed.
            for attempt in range(_FEASIBILITY_RETRIES):
                local_seed = seed + idx * 9973 + attempt * 104729
                concrete = _build_concrete(logical, row, idx=idx, local_seed=local_seed)
                if is_feasible(concrete):
                    results.append(concrete)
                    break
            idx += 1

    return results


#: How many times to re-draw the continuous parameters for a covering-array row
#: before accepting that the row cannot produce a feasible scenario.
_FEASIBILITY_RETRIES = 6


def achieved_coverage(
    logical: LogicalScenario,
    scenarios: Sequence[ConcreteScenario],
    *,
    strength: int = 2,
) -> CoverageReport:
    """Measure the t-way ODD coverage actually present in emitted scenarios.

    This is the number worth publishing: it is computed from the scenarios that
    survived feasibility checking, not from the array that was requested.
    """
    space = odd_space(logical)
    keys = set(space)
    rows: list[dict[str, Any]] = []
    for sc in scenarios:
        row: dict[str, Any] = {
            "weather": sc.weather,
            "lighting": sc.lighting,
            "road_geometry": sc.road_geometry,
        }
        for key in keys - set(ENV_DIMENSIONS):
            if key in sc.odd:
                row[key] = sc.odd[key]
        rows.append(row)
    return coverage_of(
        rows,
        space,
        strength=strength,
        forbidden=odd_forbidden(logical),
        strategy="achieved",
    )


def expand_catalog(
    logicals: list[LogicalScenario],
    *,
    target_count: int = 5000,
    seed: int = 42,
    strength: int = 2,
) -> list[ConcreteScenario]:
    """Expand the full catalog aiming for ``target_count`` concrete scenarios.

    Every logical scenario gets at least one complete pass over its covering
    array, so the pairwise guarantee holds catalog-wide regardless of the target.
    The remaining budget is distributed by crash-frequency weight, which puts
    more concrete variants behind the scenarios that cause more real crashes.
    """
    # Some catalogued scenarios have no conflict partner the kinematic layer can
    # represent. They stay in the catalog for typology completeness but must not
    # be expanded into concrete variants carrying meaningless metrics.
    logicals = [s for s in logicals if s.simulable]
    if not logicals:
        return []

    # Guarantee first: one full covering-array pass per logical scenario.
    backbone: dict[str, int] = {
        logical.id: len(_odd_combos(logical, strength=strength, seed=seed + i * 10007))
        for i, logical in enumerate(logicals)
    }
    guaranteed = sum(backbone.values())

    # Then distribute what is left in proportion to crash frequency.
    total_weight = sum(max(0.01, s.crash_frequency_weight) for s in logicals)
    surplus = max(0, target_count - guaranteed)

    all_concrete: list[ConcreteScenario] = []
    for i, logical in enumerate(logicals):
        rows = backbone[logical.id]
        share = max(0.01, logical.crash_frequency_weight) / total_weight
        budget = rows + int(round(surplus * share))
        passes = max(1, math.ceil(budget / max(1, rows)))
        batch = expand_logical(
            logical,
            samples_per_combo=passes,
            seed=seed + i * 10007,
            max_per_logical=budget,
            strength=strength,
        )
        all_concrete.extend(batch)

    # Proportional allocation rounds down, so top up the shortfall from the
    # highest-weight scenarios rather than shipping just under the target.
    ranked = sorted(logicals, key=lambda s: -s.crash_frequency_weight)
    round_no = 0
    while len(all_concrete) < target_count and round_no < 50:
        round_no += 1
        progressed = False
        for i, logical in enumerate(ranked):
            if len(all_concrete) >= target_count:
                break
            rows = backbone[logical.id]
            need = target_count - len(all_concrete)
            batch = expand_logical(
                logical,
                samples_per_combo=max(1, math.ceil(need / max(1, rows))),
                seed=seed + 99991 + round_no * 7919 + i,
                max_per_logical=min(need, rows * 4),
                strength=strength,
            )
            if not batch:
                continue
            existing = {s.id for s in all_concrete}
            for offset, s in enumerate(batch):
                s.id = f"{logical.id}__t{round_no}_{offset:04d}"
                if s.id in existing:
                    continue
                all_concrete.append(s)
                existing.add(s.id)
                progressed = True
                if len(all_concrete) >= target_count:
                    break
        if not progressed:
            break

    return all_concrete


def catalog_coverage(
    logicals: Sequence[LogicalScenario],
    scenarios: Sequence[ConcreteScenario],
    *,
    strength: int = 2,
) -> dict[str, Any]:
    """Aggregate t-way ODD coverage across the whole catalog.

    Reports per-logical coverage and the catalog-wide totals, so a shortfall in
    one scenario cannot hide inside a healthy average.
    """
    by_logical: dict[str, list[ConcreteScenario]] = {}
    for sc in scenarios:
        by_logical.setdefault(sc.logical_id, []).append(sc)

    per: dict[str, dict[str, Any]] = {}
    covered = reachable = unreachable = 0
    incomplete: list[str] = []
    # Scenarios that are never expanded cannot have ODD coverage; counting them
    # would report a permanent shortfall that no amount of generation can fix.
    for logical in [s for s in logicals if s.simulable]:
        report = achieved_coverage(
            logical, by_logical.get(logical.id, []), strength=strength
        )
        per[logical.id] = report.as_dict()
        covered += report.covered
        reachable += report.reachable
        unreachable += report.unreachable
        if not report.complete:
            incomplete.append(logical.id)

    return {
        "strength": strength,
        "covered_tuples": covered,
        "reachable_tuples": reachable,
        "unreachable_tuples": unreachable,
        "coverage_pct": round(100.0 * covered / reachable, 4) if reachable else 100.0,
        "complete": not incomplete,
        "incomplete_logicals": incomplete,
        "by_logical": per,
    }
