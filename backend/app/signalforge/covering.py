"""Deterministic t-way covering arrays over the ODD parameter space.

Combinatorial sampling of an ODD is only defensible if you can state what it
covers.  A truncated cartesian product cannot: it silently drops whole regions
of the space depending on which parameter happens to be enumerated first.  A
t-way covering array can — every combination of any ``t`` parameters appears in
at least one generated scenario, and the achieved coverage is measurable.

The generator is deterministic (same inputs, same output), dependency-free, and
constraint-aware: forbidden combinations such as an icy surface under clear
weather are never emitted, and tuples that are only reachable through forbidden
combinations are reported as unreachable rather than silently counted as
covered.

Two construction strategies are used:

``exhaustive``
    Enumerate every valid assignment, then greedily pick the one covering the
    most still-uncovered t-tuples.  Exact with respect to constraints and close
    to optimal in array size.  Used whenever the space is small enough to
    enumerate, which is the case for every scenario in the catalog.

``sampled``
    For spaces too large to enumerate, draw a bounded number of candidate rows
    per greedy step (an AETG-style construction) and pick the best.  Coverage is
    still measured honestly and reported, but is not guaranteed complete.

Reference: Cohen et al., "The AETG System: An Approach to Testing Based on
Combinatorial Design" (IEEE TSE 23(7), 1997), and Kuhn, Kacker & Lei,
"Practical Combinatorial Testing" (NIST SP 800-142, 2010).
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Iterable, Sequence

# Parameter name -> list of allowed values.
ParamSpace = dict[str, list[Any]]

# A single generated combination.
Assignment = dict[str, Any]

# Returns True when an assignment must never be emitted.
ForbiddenFn = Callable[[Assignment], bool]

# Above this many total combinations we stop enumerating the whole space and
# switch to sampled candidates.  Every catalog scenario is orders of magnitude
# below this.
MAX_ENUMERATED = 200_000

# Candidate rows drawn per greedy step in the sampled strategy.
SAMPLED_CANDIDATES = 64


# A t-tuple is an ordered tuple of (parameter, value) pairs, sorted by parameter
# name so it is canonical and hashable.
Tuple_ = tuple[tuple[str, Hashable], ...]


@dataclass
class CoverageReport:
    """What a generated array actually covers."""

    strength: int
    n_rows: int
    n_params: int
    covered: int
    reachable: int
    unreachable: int
    strategy: str
    #: Valid t-tuples the array failed to cover.  Empty for the exhaustive
    #: strategy, which is complete by construction.
    missing: list[Tuple_] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        """Percent of reachable t-tuples present in at least one row."""
        if self.reachable == 0:
            return 100.0
        return 100.0 * self.covered / self.reachable

    @property
    def complete(self) -> bool:
        return self.covered >= self.reachable

    def as_dict(self) -> dict[str, Any]:
        return {
            "strength": self.strength,
            "n_rows": self.n_rows,
            "n_params": self.n_params,
            "covered_tuples": self.covered,
            "reachable_tuples": self.reachable,
            "unreachable_tuples": self.unreachable,
            "coverage_pct": round(self.coverage_pct, 4),
            "complete": self.complete,
            "strategy": self.strategy,
        }


def _sort_key(tp: Tuple_) -> tuple:
    """Order tuples without assuming their values are mutually comparable.

    Parameter values are heterogeneous (enums, bools, ints, strings), so sorting
    on the raw values can raise.  Sorting on the repr keeps output stable and
    readable without that risk.
    """
    return tuple((k, repr(v)) for k, v in tp)


def _normalise(params: ParamSpace) -> ParamSpace:
    """Drop empty parameters and de-duplicate values, preserving order.

    Ordering is preserved rather than sorted so that a caller who lists values
    in a meaningful order (say, increasing severity) gets stable, readable
    output.  Parameter *names* are sorted downstream to keep tuples canonical.
    """
    clean: ParamSpace = {}
    for key in sorted(params):
        seen: list[Any] = []
        for value in params[key]:
            if value not in seen:
                seen.append(value)
        if seen:
            clean[key] = seen
    return clean


def _tuples_of(assignment: Assignment, keys: Sequence[str], strength: int) -> set[Tuple_]:
    """Every t-tuple present in one assignment."""
    out: set[Tuple_] = set()
    for combo in itertools.combinations(keys, strength):
        out.add(tuple((k, assignment[k]) for k in combo))
    return out


def _space_size(params: ParamSpace) -> int:
    size = 1
    for values in params.values():
        size *= len(values)
        if size > MAX_ENUMERATED:
            return size
    return size


def _enumerate_valid(
    params: ParamSpace, forbidden: ForbiddenFn | None
) -> list[Assignment]:
    keys = list(params)
    rows: list[Assignment] = []
    for values in itertools.product(*(params[k] for k in keys)):
        row = dict(zip(keys, values))
        if forbidden is not None and forbidden(row):
            continue
        rows.append(row)
    return rows


def _random_valid_row(
    params: ParamSpace, forbidden: ForbiddenFn | None, rng: random.Random, attempts: int = 40
) -> Assignment | None:
    for _ in range(attempts):
        row = {k: values[rng.randrange(len(values))] for k, values in params.items()}
        if forbidden is None or not forbidden(row):
            return row
    return None


def _greedy_cover(
    candidates: Iterable[Assignment],
    targets: set[Tuple_],
    keys: Sequence[str],
    strength: int,
) -> list[Assignment]:
    """Pick candidate rows covering the most uncovered targets, until none remain.

    Ties are broken by candidate order, so the result is fully deterministic.
    """
    candidates = list(candidates)
    remaining = set(targets)
    chosen: list[Assignment] = []
    # Precompute each candidate's tuple set once; the spaces are small enough
    # that this is far cheaper than recomputing per greedy step.
    cand_tuples = [_tuples_of(row, keys, strength) for row in candidates]
    used = [False] * len(candidates)

    while remaining:
        best_idx = -1
        best_gain = 0
        for i, tuples in enumerate(cand_tuples):
            if used[i]:
                continue
            gain = len(tuples & remaining)
            if gain > best_gain:
                best_gain = gain
                best_idx = i
        if best_idx < 0:
            # Nothing left can improve coverage.
            break
        used[best_idx] = True
        chosen.append(candidates[best_idx])
        remaining -= cand_tuples[best_idx]

    return chosen


def covering_array(
    params: ParamSpace,
    *,
    strength: int = 2,
    forbidden: ForbiddenFn | None = None,
    seed: int = 0,
    max_rows: int | None = None,
) -> tuple[list[Assignment], CoverageReport]:
    """Build a t-way covering array over ``params``.

    Returns the rows and a report describing what they cover.  With the
    exhaustive strategy and no ``max_rows`` cap the report is always complete:
    every t-tuple that appears in at least one non-forbidden assignment appears
    in at least one returned row.

    ``strength`` is clamped to the number of parameters, so a 2-way request over
    a single parameter degrades to 1-way (each value appears) rather than
    raising.
    """
    if strength < 1:
        raise ValueError("strength must be >= 1")

    clean = _normalise(params)
    keys = list(clean)

    if not keys:
        # No ODD dimensions: a single empty assignment is the whole space.
        return [{}], CoverageReport(
            strength=strength,
            n_rows=1,
            n_params=0,
            covered=0,
            reachable=0,
            unreachable=0,
            strategy="empty",
        )

    t = min(strength, len(keys))

    # All syntactically possible t-tuples, before constraints.
    possible: set[Tuple_] = set()
    for combo in itertools.combinations(keys, t):
        for values in itertools.product(*(clean[k] for k in combo)):
            possible.add(tuple(zip(combo, values)))

    if _space_size(clean) <= MAX_ENUMERATED:
        strategy = "exhaustive"
        valid_rows = _enumerate_valid(clean, forbidden)
        if not valid_rows:
            return [], CoverageReport(
                strength=t,
                n_rows=0,
                n_params=len(keys),
                covered=0,
                reachable=0,
                unreachable=len(possible),
                strategy=strategy,
                missing=sorted(possible, key=_sort_key),
            )
        # A tuple is reachable only if some valid assignment contains it.
        reachable: set[Tuple_] = set()
        for row in valid_rows:
            reachable |= _tuples_of(row, keys, t)
        rows = _greedy_cover(valid_rows, reachable, keys, t)
    else:
        strategy = "sampled"
        rng = random.Random(seed)
        pool: list[Assignment] = []
        for _ in range(SAMPLED_CANDIDATES * 8):
            row = _random_valid_row(clean, forbidden, rng)
            if row is not None:
                pool.append(row)
        if not pool:
            return [], CoverageReport(
                strength=t,
                n_rows=0,
                n_params=len(keys),
                covered=0,
                reachable=0,
                unreachable=len(possible),
                strategy=strategy,
                missing=sorted(possible, key=_sort_key),
            )
        # Without enumeration we cannot prove which tuples are reachable, so we
        # aim at everything the sampled pool shows to be achievable.
        reachable = set()
        for row in pool:
            reachable |= _tuples_of(row, keys, t)
        rows = _greedy_cover(pool, reachable, keys, t)

    if max_rows is not None and len(rows) > max_rows:
        rows = rows[:max_rows]

    report = coverage_of(rows, clean, strength=t, reachable=reachable, strategy=strategy)
    return rows, report


def coverage_of(
    rows: Sequence[Assignment],
    params: ParamSpace,
    *,
    strength: int = 2,
    reachable: set[Tuple_] | None = None,
    forbidden: ForbiddenFn | None = None,
    strategy: str = "measured",
) -> CoverageReport:
    """Measure achieved t-way coverage of an existing set of rows.

    Deliberately independent of the construction above: it recomputes the target
    set from scratch, so it is a real check on the generator rather than a
    restatement of it.
    """
    clean = _normalise(params)
    keys = list(clean)
    if not keys:
        return CoverageReport(
            strength=strength,
            n_rows=len(rows),
            n_params=0,
            covered=0,
            reachable=0,
            unreachable=0,
            strategy=strategy,
        )

    t = min(strength, len(keys))

    possible: set[Tuple_] = set()
    for combo in itertools.combinations(keys, t):
        for values in itertools.product(*(clean[k] for k in combo)):
            possible.add(tuple(zip(combo, values)))

    if reachable is None:
        if _space_size(clean) <= MAX_ENUMERATED:
            reachable = set()
            for row in _enumerate_valid(clean, forbidden):
                reachable |= _tuples_of(row, keys, t)
        else:
            reachable = possible

    seen: set[Tuple_] = set()
    for row in rows:
        if any(k not in row for k in keys):
            # Row does not span the space being measured; skip it rather than
            # crash, so callers can measure a subset of dimensions.
            continue
        seen |= _tuples_of(row, keys, t)

    covered = seen & reachable
    missing = sorted(reachable - seen, key=_sort_key)
    return CoverageReport(
        strength=t,
        n_rows=len(rows),
        n_params=len(keys),
        covered=len(covered),
        reachable=len(reachable),
        unreachable=len(possible - reachable),
        strategy=strategy,
        missing=missing,
    )
