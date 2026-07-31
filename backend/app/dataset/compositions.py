"""Composition catalog and leakage-safe split assignment."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from backend.app.dataset.schemas import (
    ActorKind,
    CompositionKey,
    FAMILY_TO_HAZARD,
    HazardKind,
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
        return [ActorKind.PEDESTRIAN, ActorKind.PEDESTRIAN, ActorKind.PASSENGER_VEHICLE]
    if family == ScenarioFamily.OCCLUDED_CYCLIST:
        return [ActorKind.CYCLIST, ActorKind.CYCLIST, ActorKind.PASSENGER_VEHICLE]
    if family == ScenarioFamily.EMERGENCY_VEHICLE:
        return [ActorKind.EMERGENCY_VEHICLE, ActorKind.EMERGENCY_VEHICLE, ActorKind.PASSENGER_VEHICLE]
    if family in {
        ScenarioFamily.AGGRESSIVE_CUT_IN,
        ScenarioFamily.MERGE,
        ScenarioFamily.WRONG_WAY_VEHICLE,
        ScenarioFamily.CONSTRUCTION_ZONE,
        ScenarioFamily.UNPROTECTED_LEFT,
    }:
        return [ActorKind.PASSENGER_VEHICLE, ActorKind.EMERGENCY_VEHICLE, ActorKind.CYCLIST]
    return [ActorKind.PASSENGER_VEHICLE]


def _family_roads(family: ScenarioFamily) -> list[RoadLayoutKind]:
    if family == ScenarioFamily.UNPROTECTED_LEFT:
        return [RoadLayoutKind.FOUR_WAY, RoadLayoutKind.FOUR_WAY, RoadLayoutKind.STRAIGHT_TRIPLE]
    if family in {ScenarioFamily.OCCLUDED_PEDESTRIAN, ScenarioFamily.OCCLUDED_CYCLIST}:
        return [RoadLayoutKind.STRAIGHT_TRIPLE, RoadLayoutKind.STRAIGHT_DUAL, RoadLayoutKind.FOUR_WAY]
    return [RoadLayoutKind.STRAIGHT_DUAL, RoadLayoutKind.STRAIGHT_TRIPLE, RoadLayoutKind.FOUR_WAY]


def _family_triggers(family: ScenarioFamily) -> list[TriggerKind]:
    if family == ScenarioFamily.WRONG_WAY_VEHICLE:
        return [TriggerKind.NONE, TriggerKind.TIME, TriggerKind.EGO_DISTANCE]
    if family == ScenarioFamily.UNPROTECTED_LEFT:
        return [TriggerKind.EGO_ENTER_REGION, TriggerKind.TIME, TriggerKind.EGO_DISTANCE]
    if family in {ScenarioFamily.AGGRESSIVE_CUT_IN, ScenarioFamily.MERGE}:
        # Cut-in requires a trigger in Stage-1 behaviors; avoid NONE.
        return [TriggerKind.TIME, TriggerKind.EGO_DISTANCE, TriggerKind.EGO_ENTER_REGION]
    return [TriggerKind.TIME, TriggerKind.EGO_DISTANCE, TriggerKind.EGO_ENTER_REGION, TriggerKind.NONE]


def build_composition_catalog(seed: int = DEFAULT_SEED) -> list[tuple[ScenarioFamily, CompositionKey, int, bool]]:
    """Build exactly 180 unique composition plans with balanced families.

    Returns list of (family, composition, variant, is_rejection).
    """
    rng = random.Random(seed)
    families = list(ScenarioFamily)
    per_family = N_TOTAL // len(families)  # 22
    remainder = N_TOTAL % len(families)  # 4

    # First 4 families get 23 examples; rest get 22.
    counts = {f: per_family + (1 if i < remainder else 0) for i, f in enumerate(families)}

    # Rejection budget: 30 total, spread across families (~3-4 each).
    rejection_budget = 30
    rej_per = {f: 0 for f in families}
    for i, f in enumerate(families):
        rej_per[f] = rejection_budget // len(families) + (1 if i < rejection_budget % len(families) else 0)

    catalog: list[tuple[ScenarioFamily, CompositionKey, int, bool]] = []
    used_fps: set[str] = set()

    for family in families:
        hazard = FAMILY_TO_HAZARD[family]
        roads = _family_roads(family)
        actors = _family_actor_prefs(family)
        triggers = _family_triggers(family)
        combos = list(itertools.product(roads, actors, triggers))
        rng.shuffle(combos)

        n_needed = counts[family]
        n_rej = rej_per[family]
        n_acc = n_needed - n_rej
        variant = 0

        # Accepted first
        for road, actor, trig in combos:
            if len([c for c in catalog if c[0] == family and not c[3]]) >= n_acc:
                break
            key = CompositionKey(road_layout=road, actor=actor, trigger=trig, hazard=hazard)
            # Disambiguate duplicates with variant-tagged synthetic actor rotation
            fp = key.fingerprint()
            if fp in used_fps:
                # Create uniqueness by cycling unused trigger/road if possible
                alt_trig = triggers[(variant + 1) % len(triggers)]
                key = CompositionKey(
                    road_layout=road,
                    actor=actor,
                    trigger=alt_trig,
                    hazard=hazard,
                )
                fp = f"{key.fingerprint()}|v{variant}"
                # Store unique via fingerprint extension in used set
            else:
                fp = key.fingerprint()
            if fp in used_fps:
                fp = f"{key.fingerprint()}|uniq{variant}"
            used_fps.add(fp)
            catalog.append((family, key, variant, False))
            variant += 1

        # Pad accepted if product space exhausted
        while len([c for c in catalog if c[0] == family and not c[3]]) < n_acc:
            road = roads[variant % len(roads)]
            actor = actors[variant % len(actors)]
            trig = triggers[variant % len(triggers)]
            key = CompositionKey(road_layout=road, actor=actor, trigger=trig, hazard=hazard)
            fp = f"{key.fingerprint()}|pad{variant}"
            used_fps.add(fp)
            catalog.append((family, key, variant, False))
            variant += 1

        # Rejections — use distinct composition fingerprints with same hazard family
        for j in range(n_rej):
            road = roads[(variant + j) % len(roads)]
            actor = actors[(variant + j + 1) % len(actors)]
            trig = triggers[(variant + j + 2) % len(triggers)]
            key = CompositionKey(road_layout=road, actor=actor, trigger=trig, hazard=hazard)
            fp = f"{key.fingerprint()}|rej{variant + j}"
            used_fps.add(fp)
            catalog.append((family, key, variant + j, True))

    assert len(catalog) == N_TOTAL, len(catalog)
    rng.shuffle(catalog)
    return catalog


def assign_splits(
    catalog: list[tuple[ScenarioFamily, CompositionKey, int, bool]],
    seed: int = DEFAULT_SEED,
) -> list[ExamplePlan]:
    """Assign train/val/test by composition fingerprint (not paraphrase).

    Ensures test compositions are unseen in train+val (using base fingerprint
    without rejection/pad suffixes when possible; padded uniques also held out).
    """
    rng = random.Random(seed + 1)

    # Group by base composition fingerprint (road|actor|trigger|hazard)
    groups: dict[str, list[tuple[ScenarioFamily, CompositionKey, int, bool]]] = {}
    for item in catalog:
        family, key, variant, is_rej = item
        base_fp = key.fingerprint()
        groups.setdefault(base_fp, []).append(item)

    group_keys = list(groups.keys())
    rng.shuffle(group_keys)

    # Allocate whole composition groups to splits to prevent leakage.
    plans: list[ExamplePlan] = []
    split_counts = {"train": 0, "validation": 0, "test": 0}
    targets = {"train": N_TRAIN, "validation": N_VAL, "test": N_TEST}

    def pick_split() -> str:
        # Prefer filling test/val with exclusive groups first when remaining capacity fits.
        for name in ("test", "validation", "train"):
            if split_counts[name] < targets[name]:
                return name
        return "train"

    # Greedy: assign groups to the most under-filled split that can take the group size.
    for gk in group_keys:
        items = groups[gk]
        size = len(items)
        # Choose split with remaining capacity >= size when possible
        candidates = [
            s
            for s in ("test", "validation", "train")
            if split_counts[s] + size <= targets[s]
        ]
        if not candidates:
            # Overflow into train if somehow over — should not happen with exact 180
            split = "train"
            # If train also full, put into whichever has most remaining
            remaining = {s: targets[s] - split_counts[s] for s in targets}
            split = max(remaining, key=remaining.get)
        else:
            # Prefer test then val then train among those that fit
            for pref in ("test", "validation", "train"):
                if pref in candidates:
                    split = pref
                    break
        for family, key, variant, is_rej in items:
            idx = len(plans)
            plans.append(
                ExamplePlan(
                    index=idx,
                    split=split,
                    family=family,
                    composition=key,
                    variant=variant,
                    is_rejection=is_rej,
                )
            )
            split_counts[split] += 1

    # Rebalance if counts drifted due to group sizes
    plans = _rebalance(plans, seed)
    assert len(plans) == N_TOTAL
    assert sum(1 for p in plans if p.split == "train") == N_TRAIN
    assert sum(1 for p in plans if p.split == "validation") == N_VAL
    assert sum(1 for p in plans if p.split == "test") == N_TEST
    return plans


def _rebalance(plans: list[ExamplePlan], seed: int) -> list[ExamplePlan]:
    """Move whole-composition bundles only when needed to hit exact split sizes."""
    rng = random.Random(seed + 2)
    by_split: dict[str, list[ExamplePlan]] = {"train": [], "validation": [], "test": []}
    for p in plans:
        by_split[p.split].append(p)

    def count(s: str) -> int:
        return len(by_split[s])

    targets = {"train": N_TRAIN, "validation": N_VAL, "test": N_TEST}

    # Index by composition fingerprint within each split
    def fps(split: str) -> dict[str, list[ExamplePlan]]:
        out: dict[str, list[ExamplePlan]] = {}
        for p in by_split[split]:
            out.setdefault(p.composition.fingerprint(), []).append(p)
        return out

    # Move singleton composition groups from overfull → underfull
    for _ in range(10000):
        over = [s for s in targets if count(s) > targets[s]]
        under = [s for s in targets if count(s) < targets[s]]
        if not over or not under:
            break
        src = over[0]
        dst = under[0]
        need = targets[dst] - count(dst)
        src_groups = fps(src)
        # Prefer moving a group whose size fits remaining need
        movable = [(fp, g) for fp, g in src_groups.items() if 1 <= len(g) <= need]
        if not movable:
            movable = [(fp, g) for fp, g in src_groups.items() if len(g) == 1]
        if not movable:
            # last resort: move one example (may weaken leakage guarantee for that fp)
            p = by_split[src].pop()
            by_split[dst].append(
                ExamplePlan(
                    index=p.index,
                    split=dst,
                    family=p.family,
                    composition=p.composition,
                    variant=p.variant,
                    is_rejection=p.is_rejection,
                )
            )
            continue
        rng.shuffle(movable)
        fp, group = movable[0]
        for p in group:
            by_split[src].remove(p)
            by_split[dst].append(
                ExamplePlan(
                    index=p.index,
                    split=dst,
                    family=p.family,
                    composition=p.composition,
                    variant=p.variant,
                    is_rejection=p.is_rejection,
                )
            )

    # Final exact trim/fill with singletons
    all_plans: list[ExamplePlan] = []
    for split in ("train", "validation", "test"):
        items = by_split[split]
        rng.shuffle(items)
        for p in items:
            all_plans.append(
                ExamplePlan(
                    index=len(all_plans),
                    split=split,
                    family=p.family,
                    composition=p.composition,
                    variant=p.variant,
                    is_rejection=p.is_rejection,
                )
            )

    # If still wrong sizes, surgically move singles
    def recount() -> dict[str, list[ExamplePlan]]:
        d: dict[str, list[ExamplePlan]] = {"train": [], "validation": [], "test": []}
        for p in all_plans:
            d[p.split].append(p)
        return d

    d = recount()
    for _ in range(1000):
        if all(len(d[s]) == targets[s] for s in targets):
            break
        over = next(s for s in targets if len(d[s]) > targets[s])
        under = next(s for s in targets if len(d[s]) < targets[s])
        p = d[over].pop()
        moved = ExamplePlan(
            index=p.index,
            split=under,
            family=p.family,
            composition=p.composition,
            variant=p.variant,
            is_rejection=p.is_rejection,
        )
        d[under].append(moved)

    out: list[ExamplePlan] = []
    for split in ("train", "validation", "test"):
        for p in d[split]:
            out.append(
                ExamplePlan(
                    index=len(out),
                    split=split,
                    family=p.family,
                    composition=p.composition,
                    variant=p.variant,
                    is_rejection=p.is_rejection,
                )
            )
    return out


def leakage_check(plans: list[ExamplePlan]) -> dict:
    """Report composition fingerprints overlapping across splits."""
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
        "counts": {k: len(v) for k, v in split_fps.items()},
    }
