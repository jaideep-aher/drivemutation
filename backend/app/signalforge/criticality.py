"""Search a logical scenario's parameter space for the scenarios that matter.

Most randomly-sampled concrete scenarios are benign: two vehicles cruise past
each other and nothing is learned.  The informative ones sit at the *criticality
boundary* — the parameter values where the reference driver only just copes, and
a hair's change tips the scenario into an unavoidable collision.

The boundary is defined against the SUT-neutral
:class:`~backend.app.signalforge.reference_driver.ReferenceDriver`, never against
a system under test.  This is the whole point: a scenario tuned until it defeats
one particular planner measures that planner, not the world.  A scenario tuned to
the edge of what a competent driver can manage is a fair test for anyone, and
stays valid as stacks change.

The search is a thin loop over the existing kinematic simulator, which runs in
well under a millisecond, so exhaustive-enough coverage is affordable:

1. **Grid** — evaluate a coarse lattice over the continuous parameters
   (ego speed, challenger speed, initial gap) for each discrete ODD row.
2. **Bisect** — where neighbouring grid points straddle the boundary (one
   survivable, one not), bisect the segment between them to locate it precisely.

Both stages are deterministic, so a reported boundary can be reproduced exactly.
"""

from __future__ import annotations

import itertools
import random
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from backend.app.signalforge.expand import _build_concrete, _odd_combos
from backend.app.signalforge.reference_driver import ReferenceDriver
from backend.app.signalforge.schema import ConcreteScenario, LogicalScenario
from backend.app.signalforge.sim import simulate

#: Continuous parameters the search varies.
AXES = ("ego_speed_kph", "actor_speed_kph", "distance_m")

#: Clearance at or below this counts as a collision for boundary purposes.
CONTACT_CLEARANCE_M = 0.0

#: Bisection stops once the bracket is this small, as a fraction of the axis range.
DEFAULT_BISECTION_TOLERANCE = 0.005

#: Bisection iteration cap, so a pathological objective cannot spin.
MAX_BISECTION_STEPS = 40


@dataclass(frozen=True)
class Sample:
    """One evaluated point in a logical scenario's parameter space."""

    params: dict[str, float]
    odd: dict[str, Any]
    min_clearance_m: float
    min_ttc_s: float | None
    required_decel_mps2: float | None
    collision: bool
    preventable: bool | None
    difficulty: str

    @property
    def survivable(self) -> bool:
        """Whether the reference driver got through without contact."""
        return self.min_clearance_m > CONTACT_CLEARANCE_M

    def as_dict(self) -> dict[str, Any]:
        return {
            "params": {k: round(v, 4) for k, v in self.params.items()},
            "odd": {k: v for k, v in self.odd.items()},
            "min_clearance_m": round(self.min_clearance_m, 4),
            "min_ttc_s": round(self.min_ttc_s, 4) if self.min_ttc_s is not None else None,
            "required_decel_mps2": (
                round(self.required_decel_mps2, 4)
                if self.required_decel_mps2 is not None
                else None
            ),
            "collision": self.collision,
            "preventable": self.preventable,
            "difficulty": self.difficulty,
            "survivable": self.survivable,
        }


@dataclass
class CriticalityResult:
    """What the search found for one logical scenario."""

    logical_id: str
    evaluations: int
    driver: dict[str, float | str]
    #: Hardest point the reference driver still survived, by smallest clearance.
    tightest_survivable: Sample | None = None
    #: Easiest point it failed, by largest clearance — just past the boundary.
    easiest_failure: Sample | None = None
    #: Points located on the boundary by bisection.
    boundary: list[Sample] = field(default_factory=list)
    #: True when every sampled point survived, so no boundary exists in range.
    always_survivable: bool = False
    #: True when no sampled point survived.
    never_survivable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "logical_id": self.logical_id,
            "evaluations": self.evaluations,
            "reference_driver": self.driver,
            "tightest_survivable": (
                self.tightest_survivable.as_dict() if self.tightest_survivable else None
            ),
            "easiest_failure": (
                self.easiest_failure.as_dict() if self.easiest_failure else None
            ),
            "boundary": [s.as_dict() for s in self.boundary],
            "always_survivable": self.always_survivable,
            "never_survivable": self.never_survivable,
        }


def _axis_values(low: float, high: float, steps: int) -> list[float]:
    """``steps`` evenly spaced values across a range, inclusive of both ends."""
    if steps <= 1 or high <= low:
        return [low]
    span = high - low
    return [low + span * i / (steps - 1) for i in range(steps)]


def _ranges(logical: LogicalScenario) -> dict[str, tuple[float, float]]:
    return {
        "ego_speed_kph": (logical.ego_speed_kph.min, logical.ego_speed_kph.max),
        "actor_speed_kph": (logical.actor_speed_kph.min, logical.actor_speed_kph.max),
        "distance_m": (logical.distance_m.min, logical.distance_m.max),
    }


def layout_seed(logical: LogicalScenario, odd_row: dict[str, Any]) -> int:
    """A stable seed for one (logical scenario, ODD row) pair.

    The actor layout has genuinely random elements — which side a cut-in comes
    from, when a brake is triggered — and a search only makes sense if the same
    parameters always produce the same scenario.  Seeding from the evaluation
    index instead would make the objective noisy, and bisection would chase that
    noise rather than the criticality boundary.
    """
    # zlib.crc32 rather than hash(): Python randomises string hashing per
    # process, so hash() would give a different layout on every run and the
    # "reproducible boundary" claim would be false.
    parts = [logical.id] + [f"{k}={v}" for k, v in sorted(odd_row.items())]
    return zlib.crc32("|".join(parts).encode()) % (2**31)


def build_scenario(
    logical: LogicalScenario,
    params: dict[str, float],
    odd_row: dict[str, Any],
    *,
    index: int = 0,
    seed: int | None = None,
) -> ConcreteScenario:
    """Instantiate a concrete scenario at exact parameter values.

    The normal expansion path samples the continuous parameters from a seed; a
    search needs to pin them, so this reuses the same layout code with the
    sampling stage bypassed.
    """
    stable = layout_seed(logical, odd_row) if seed is None else seed
    scenario = _build_concrete(logical, odd_row, idx=index, local_seed=stable)
    return _retarget(logical, scenario, params, odd_row, stable)


def _retarget(
    logical: LogicalScenario,
    template: ConcreteScenario,
    params: dict[str, float],
    odd_row: dict[str, Any],
    seed: int,
) -> ConcreteScenario:
    """Rebuild a scenario's layout at the requested continuous parameters."""
    from backend.app.signalforge.expand import _actor_layout  # local: avoids a cycle

    rng = random.Random(seed)
    odd = {k: v for k, v in template.odd.items()}
    ego, actors = _actor_layout(
        logical,
        params["ego_speed_kph"],
        params["actor_speed_kph"],
        params["distance_m"],
        odd,
        rng,
    )
    return template.model_copy(update={"ego": ego, "actors": actors, "odd": odd})


def evaluate(
    logical: LogicalScenario,
    params: dict[str, float],
    odd_row: dict[str, Any],
    *,
    driver: ReferenceDriver,
    index: int = 0,
) -> Sample:
    """Run one point through the simulator under the reference driver."""
    scenario = build_scenario(logical, params, odd_row, index=index)
    result = simulate(scenario, reference_driver=driver)
    metrics = result.metrics
    clearance = metrics.min_clearance_m
    if clearance is None:
        # No actors to conflict with; treat as unboundedly safe.
        clearance = float("inf")
    return Sample(
        params=dict(params),
        odd={k: v for k, v in odd_row.items()},
        min_clearance_m=clearance,
        min_ttc_s=metrics.min_ttc_s,
        required_decel_mps2=metrics.required_decel_mps2,
        collision=metrics.collision,
        preventable=metrics.preventable,
        difficulty=result.difficulty.value,
    )


def _bisect(
    logical: LogicalScenario,
    safe: Sample,
    unsafe: Sample,
    odd_row: dict[str, Any],
    *,
    driver: ReferenceDriver,
    tolerance: float,
    counter: list[int],
) -> Sample:
    """Locate the boundary between a survivable and an unsurvivable point.

    Interpolates along the straight line joining them, halving the bracket until
    the two ends are within ``tolerance`` of each other in normalised parameter
    space.  Returns the tightest point still survivable.
    """
    ranges = _ranges(logical)
    low, high = 0.0, 1.0
    best = safe

    for _ in range(MAX_BISECTION_STEPS):
        if high - low <= tolerance:
            break
        mid = (low + high) / 2.0
        params = {
            axis: safe.params[axis] + mid * (unsafe.params[axis] - safe.params[axis])
            for axis in AXES
        }
        # Keep the interpolated point inside the declared range.
        for axis, (axis_lo, axis_hi) in ranges.items():
            params[axis] = min(max(params[axis], axis_lo), axis_hi)

        counter[0] += 1
        sample = evaluate(logical, params, odd_row, driver=driver, index=counter[0])
        if sample.survivable:
            best = sample
            low = mid
        else:
            high = mid

    return best


def search_logical(
    logical: LogicalScenario,
    *,
    driver: ReferenceDriver | None = None,
    grid_steps: int = 5,
    max_odd_rows: int = 8,
    tolerance: float = DEFAULT_BISECTION_TOLERANCE,
    seed: int = 0,
) -> CriticalityResult:
    """Find the criticality boundary for one logical scenario.

    ``grid_steps`` controls the coarse lattice per continuous axis, so the grid
    costs ``grid_steps ** 3`` simulations per ODD row.  ``max_odd_rows`` bounds
    how many discrete ODD combinations are explored, taken from the same covering
    array the generator uses so the sampled rows are still representative.
    """
    driver = driver or ReferenceDriver()
    ranges = _ranges(logical)
    axis_values = {
        axis: _axis_values(low, high, grid_steps) for axis, (low, high) in ranges.items()
    }

    odd_rows = _odd_combos(logical, seed=seed)[:max_odd_rows] or [{}]

    counter = [0]
    tightest_survivable: Sample | None = None
    easiest_failure: Sample | None = None
    boundary: list[Sample] = []

    for odd_row in odd_rows:
        grid: list[Sample] = []
        for combo in itertools.product(*(axis_values[axis] for axis in AXES)):
            params = dict(zip(AXES, combo))
            counter[0] += 1
            sample = evaluate(logical, params, odd_row, driver=driver, index=counter[0])
            grid.append(sample)

            if sample.survivable:
                if (
                    tightest_survivable is None
                    or sample.min_clearance_m < tightest_survivable.min_clearance_m
                ):
                    tightest_survivable = sample
            else:
                if (
                    easiest_failure is None
                    or sample.min_clearance_m > easiest_failure.min_clearance_m
                ):
                    easiest_failure = sample

        # Bisect between the closest survivable/unsurvivable pair in this row.
        survivors = [s for s in grid if s.survivable]
        failures = [s for s in grid if not s.survivable]
        if survivors and failures:
            safe = min(survivors, key=lambda s: s.min_clearance_m)
            unsafe = max(failures, key=lambda s: s.min_clearance_m)
            boundary.append(
                _bisect(
                    logical,
                    safe,
                    unsafe,
                    odd_row,
                    driver=driver,
                    tolerance=tolerance,
                    counter=counter,
                )
            )

    # ODD rows that differ only in dimensions the kinematics ignore (occlusion,
    # say) land on the same boundary point; report it once.
    deduped: list[Sample] = []
    seen: set[tuple] = set()
    for sample in boundary:
        key = tuple(round(sample.params[axis], 3) for axis in AXES)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sample)
    boundary = sorted(deduped, key=lambda s: s.min_clearance_m)

    return CriticalityResult(
        logical_id=logical.id,
        evaluations=counter[0],
        driver=driver.describe(),
        tightest_survivable=tightest_survivable,
        easiest_failure=easiest_failure,
        boundary=boundary,
        always_survivable=easiest_failure is None,
        never_survivable=tightest_survivable is None,
    )


def search_catalog(
    logicals: Iterable[LogicalScenario],
    *,
    driver: ReferenceDriver | None = None,
    grid_steps: int = 5,
    max_odd_rows: int = 4,
    seed: int = 0,
) -> list[CriticalityResult]:
    """Run the search across a catalog, skipping scenarios that cannot be simulated."""
    results = []
    for logical in logicals:
        if not logical.simulable:
            continue
        results.append(
            search_logical(
                logical,
                driver=driver,
                grid_steps=grid_steps,
                max_odd_rows=max_odd_rows,
                seed=seed,
            )
        )
    return results


def boundary_scenarios(
    results: Sequence[CriticalityResult],
    logicals: Sequence[LogicalScenario],
) -> list[ConcreteScenario]:
    """Materialise the located boundary points as concrete scenarios.

    These are the scenarios worth shipping as a hard subset: each one is the
    tightest case its logical scenario offers that a competent driver still
    survives.
    """
    by_id = {s.id: s for s in logicals}
    out: list[ConcreteScenario] = []
    for i, result in enumerate(results):
        logical = by_id.get(result.logical_id)
        if logical is None:
            continue
        for j, sample in enumerate(result.boundary):
            scenario = build_scenario(
                logical, sample.params, sample.odd, index=i * 1000 + j
            )
            scenario.id = f"{logical.id}__critical_{j:02d}"
            simulated = simulate(scenario)
            scenario.metrics = simulated.metrics
            scenario.difficulty = simulated.difficulty
            scenario.provenance = scenario.provenance.model_copy(
                update={
                    "notes": (
                        f"{scenario.provenance.notes} "
                        "Parameters located by criticality search at the boundary of "
                        "what the R157 reference driver can avoid."
                    ).strip()
                }
            )
            out.append(scenario)
    return out
