#!/usr/bin/env python3
"""Find the criticality boundary of each logical scenario.

Criticality is measured against the SUT-neutral R157 reference driver, so the
result describes the scenario rather than any particular stack. The boundary is
where a competent driver only just avoids contact; a hair further and the
collision is unavoidable.

    python scripts/search_criticality.py --grid 5 --odd-rows 3

Writes a JSON report and, with ``--save-scenarios``, the boundary points as
concrete scenarios that can be exported to OpenSCENARIO like any other.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.signalforge import store
from backend.app.signalforge.catalog import build_catalog, simulable_catalog
from backend.app.signalforge.criticality import boundary_scenarios, search_catalog
from backend.app.signalforge.reference_driver import ReferenceDriver


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=int, default=5, help="Grid steps per continuous axis")
    parser.add_argument("--odd-rows", type=int, default=3, help="ODD rows to explore per scenario")
    parser.add_argument("--logical", default=None, help="Only search this logical scenario id")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "signalforge" / "catalog" / "criticality.json",
    )
    parser.add_argument(
        "--save-scenarios",
        action="store_true",
        help="Also write the boundary points as concrete scenarios",
    )
    # The reference driver is the yardstick; exposing it makes the sensitivity
    # of the boundary to driver assumptions inspectable rather than hidden.
    parser.add_argument("--reaction", type=float, default=None, help="Override reaction time (s)")
    parser.add_argument(
        "--max-decel", type=float, default=None, help="Override braking bound (m/s^2)"
    )
    args = parser.parse_args()

    logicals = simulable_catalog()
    if args.logical:
        logicals = [s for s in logicals if s.id == args.logical]
        if not logicals:
            print(f"No simulable logical scenario with id {args.logical}", file=sys.stderr)
            return 1

    driver_kwargs = {}
    if args.reaction is not None:
        driver_kwargs["reaction_s"] = args.reaction
    if args.max_decel is not None:
        driver_kwargs["max_decel_mps2"] = args.max_decel
    driver = ReferenceDriver(**driver_kwargs)

    print(f"Reference driver: {json.dumps(driver.describe())}")
    print(f"Searching {len(logicals)} logical scenarios (grid={args.grid}, odd_rows={args.odd_rows})…")

    started = time.time()
    results = search_catalog(
        logicals, driver=driver, grid_steps=args.grid, max_odd_rows=args.odd_rows
    )
    elapsed = time.time() - started

    total_sims = sum(r.evaluations for r in results)
    with_boundary = [r for r in results if r.boundary]
    always = [r.logical_id for r in results if r.always_survivable]
    never = [r.logical_id for r in results if r.never_survivable]

    print(f"  {total_sims} simulations in {elapsed:.1f}s")
    print(f"  {len(with_boundary)}/{len(results)} scenarios have a criticality boundary")
    if always:
        print(f"  always survivable within declared ranges ({len(always)}): {', '.join(always)}")
    if never:
        print(f"  never survivable within declared ranges ({len(never)}): {', '.join(never)}")

    print("\nTightest boundary per scenario:")
    for result in sorted(
        with_boundary, key=lambda r: r.boundary[0].min_clearance_m if r.boundary else 1e9
    ):
        best = result.boundary[0]
        print(
            f"  {result.logical_id:48s} clearance={best.min_clearance_m:7.4f} m  "
            f"ego={best.params['ego_speed_kph']:6.1f} kph  "
            f"actor={best.params['actor_speed_kph']:6.1f} kph  "
            f"gap={best.params['distance_m']:6.1f} m"
        )

    report = {
        "reference_driver": driver.describe(),
        "grid_steps": args.grid,
        "odd_rows": args.odd_rows,
        "total_simulations": total_sims,
        "elapsed_s": round(elapsed, 3),
        "scenarios_with_boundary": len(with_boundary),
        "always_survivable": always,
        "never_survivable": never,
        "results": [r.as_dict() for r in results],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nReport: {args.out}")

    if args.save_scenarios:
        scenarios = boundary_scenarios(results, build_catalog())
        path = args.out.parent / "critical_scenarios.json"
        path.write_text(
            json.dumps([s.model_dump(mode="json") for s in scenarios], indent=2) + "\n"
        )
        print(f"Boundary scenarios ({len(scenarios)}): {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
