"""Composition catalog and leakage-safe split assignment."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from backend.app.dataset.schemas import (
    ActorKind,
    CompositionKey,
    FAMILY_TO_HAZARD,
    RoadLayoutKind,
    ScenarioFamily,
    TriggerKind,
)

DEFAULT_SEED = 20260730
N_TRAIN = 120
N_VAL = 30
N_TEST = 30
N_TOTAL = N_TRAIN + N_VAL + N_TEST  # 180


@dataclass(frozen=True)
class ExamplePlan:
    index: int
    split: str
    family: ScenarioFamily
    composition: CompositionKey
    variant: int
    is_rejection: bool


def _family_actor_prefs(family: ScenarioFamily) -> list[ActorKind]:
    if family == ScenarioFamily.OCCLUDED_PEDESTRIAN:
        return [ActorKind.PEDESTRIAN, ActorKind.PASSENGER_VEHICLE, ActorKind.CYCLIST, ActorKind.EMERGENCY_VEHICLE]
    if family == ScenarioFamily.OCCLUDED_CYCLIST:
        return [ActorKind.CYCLIST, ActorKind.PASSENGER_VEHICLE, ActorKind.PEDESTRIAN, ActorKind.EMERGENCY_VEHICLE]
    if family == ScenarioFamily.EMERGENCY_VEHICLE:
        return [ActorKind.EMERGENCY_VEHICLE, ActorKind.PASSENGER_VEHICLE, ActorKind.CYCLIST, ActorKind.PEDESTRIAN]
    return [ActorKind.PASSENGER_VEHICLE, ActorKind.EMERGENCY_VEHICLE, ActorKind.CYCLIST, ActorKind.PEDESTRIAN]


def _family_roads(family: ScenarioFamily) -> list[RoadLayoutKind]:
    if family == ScenarioFamily.UNPROTECTED_LEFT:
        # Prefer four-way but allow others for composition diversity
        return [RoadLayoutKind.FOUR_WAY, RoadLayoutKind.STRAIGHT_TRIPLE, RoadLayoutKind.STRAIGHT_DUAL]
    return [RoadLayoutKind.STRAIGHT_DUAL, RoadLayoutKind.STRAIGHT_TRIPLE, RoadLayoutKind.FOUR_WAY]


def _family_triggers(family: ScenarioFamily) -> list[TriggerKind]:
    if family == ScenarioFamily.WRONG_WAY_VEHICLE:
        return [TriggerKind.NONE, TriggerKind.TIME, TriggerKind.EGO_DISTANCE, TriggerKind.EGO_ENTER_REGION]
    if family in {ScenarioFamily.AGGRESSIVE_CUT_IN, ScenarioFamily.MERGE}:
        # Cut-in behaviors require a trigger id in Stage 1.
        return [TriggerKind.TIME, TriggerKind.EGO_DISTANCE, TriggerKind.EGO_ENTER_REGION]
    if family == ScenarioFamily.UNPROTECTED_LEFT:
        return [TriggerKind.EGO_ENTER_REGION, TriggerKind.TIME, TriggerKind.EGO_DISTANCE, TriggerKind.NONE]
    return [TriggerKind.TIME, TriggerKind.EGO_DISTANCE, TriggerKind.EGO_ENTER_REGION, TriggerKind.NONE]


def build_composition_catalog(
    seed: int = DEFAULT_SEED,
) -> list[tuple[ScenarioFamily, CompositionKey, int, bool]]:
    """Build exactly 180 examples with unique composition fingerprints."""
    rng = random.Random(seed)
    families = list(ScenarioFamily)
    per_family = N_TOTAL // len(families)  # 22
    remainder = N_TOTAL % len(families)  # 4
    counts = {f: per_family + (1 if i < remainder else 0) for i, f in enumerate(families)}

    rejection_budget = 30
    rej_per = {
        f: rejection_budget // len(families)
        + (1 if i < rejection_budget % len(families) else 0)
        for i, f in enumerate(families)
    }

    used: set[str] = set()
    catalog: list[tuple[ScenarioFamily, CompositionKey, int, bool]] = []

    for family in families:
        hazard = FAMILY_TO_HAZARD[family]
        roads = _family_roads(family)
        actors = _family_actor_prefs(family)
        triggers = _family_triggers(family)
        combos = [
            CompositionKey(road_layout=r, actor=a, trigger=t, hazard=hazard)
            for r, a, t in itertools.product(roads, actors, triggers)
        ]
        rng.shuffle(combos)
        available = [c for c in combos if c.fingerprint() not in used]
        n_needed = counts[family]
        if len(available) < n_needed:
            raise RuntimeError(
                f"Insufficient unique compositions for {family.value}: "
                f"{len(available)} < {n_needed}"
            )

        chosen = available[:n_needed]
        n_rej = rej_per[family]
        # Mark last n_rej as rejections (deterministic after shuffle)
        for i, key in enumerate(chosen):
            used.add(key.fingerprint())
            is_rej = i >= (n_needed - n_rej)
            catalog.append((family, key, i, is_rej))

    assert len(catalog) == N_TOTAL
    assert len(used) == N_TOTAL
    rng.shuffle(catalog)
    return catalog


def assign_splits(
    catalog: list[tuple[ScenarioFamily, CompositionKey, int, bool]],
    seed: int = DEFAULT_SEED,
) -> list[ExamplePlan]:
    """Assign splits by unique composition — no fingerprint appears in two splits."""
    rng = random.Random(seed + 1)
    items = list(catalog)
    rng.shuffle(items)

    # Stratify lightly by family while filling exact quotas
    train: list = []
    val: list = []
    test: list = []

    # Round-robin families into buckets then slice
    by_family: dict[ScenarioFamily, list] = {f: [] for f in ScenarioFamily}
    for item in items:
        by_family[item[0]].append(item)

    # Take proportional test/val from each family first
    for family in ScenarioFamily:
        bucket = by_family[family]
        rng.shuffle(bucket)
        # ~1/6 to test, ~1/6 to val, rest train (180 total → 30/30/120)
        n = len(bucket)
        n_test = max(1, round(n * N_TEST / N_TOTAL))
        n_val = max(1, round(n * N_VAL / N_TOTAL))
        # Adjust later for exact totals
        test.extend(bucket[:n_test])
        val.extend(bucket[n_test : n_test + n_val])
        train.extend(bucket[n_test + n_val :])

    def _trim(dst: list, target: int, spill: list) -> None:
        while len(dst) > target:
            spill.append(dst.pop())

    def _fill(dst: list, target: int, source: list) -> None:
        while len(dst) < target and source:
            dst.append(source.pop())

    # Fix exact counts: prefer moving between train <-> val/test
    _trim(test, N_TEST, train)
    _trim(val, N_VAL, train)
    _fill(test, N_TEST, train)
    _fill(val, N_VAL, train)
    # If still short (shouldn't), pull from the other holdout
    if len(test) < N_TEST:
        _fill(test, N_TEST, val)
    if len(val) < N_VAL:
        _fill(val, N_VAL, test if len(test) > N_TEST else train)

    # Final surgical balance
    pools = {"train": train, "validation": val, "test": test}
    targets = {"train": N_TRAIN, "validation": N_VAL, "test": N_TEST}
    for _ in range(1000):
        if all(len(pools[s]) == targets[s] for s in targets):
            break
        over = next(s for s in targets if len(pools[s]) > targets[s])
        under = next(s for s in targets if len(pools[s]) < targets[s])
        pools[under].append(pools[over].pop())

    assert len(train) == N_TRAIN and len(val) == N_VAL and len(test) == N_TEST

    plans: list[ExamplePlan] = []
    for split, bucket in (
        ("train", train),
        ("validation", val),
        ("test", test),
    ):
        for family, key, variant, is_rej in bucket:
            plans.append(
                ExamplePlan(
                    index=len(plans),
                    split=split,
                    family=family,
                    composition=key,
                    variant=variant,
                    is_rejection=is_rej,
                )
            )
    return plans


def leakage_check(plans: list[ExamplePlan]) -> dict:
    split_fps: dict[str, set[str]] = {"train": set(), "validation": set(), "test": set()}
    for p in plans:
        split_fps[p.split].add(p.composition.fingerprint())

    train_val = split_fps["train"] & split_fps["validation"]
    train_test = split_fps["train"] & split_fps["test"]
    val_test = split_fps["validation"] & split_fps["test"]
    return {
        "train_validation_overlap": sorted(train_val),
        "train_test_overlap": sorted(train_test),
        "validation_test_overlap": sorted(val_test),
        "has_train_test_leakage": bool(train_test),
        "has_any_cross_split_leakage": bool(train_val or train_test or val_test),
        "unique_compositions": len(split_fps["train"] | split_fps["validation"] | split_fps["test"]),
        "counts": {k: len(v) for k, v in split_fps.items()},
    }
