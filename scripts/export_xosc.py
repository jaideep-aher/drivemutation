#!/usr/bin/env python3
"""Export SignalForge scenarios as ASAM OpenSCENARIO (.xosc) bundles.

Each scenario becomes a ``.xosc`` plus the ``.xodr`` road it references, so a
bundle runs anywhere without SignalForge installed:

    esmini --window 60 60 800 400 --osc <scenario>.xosc

Scenarios come from the generated store by default; ``--from-catalog`` expands
the logical catalog on the fly instead, which is handy before a full generation
run has been done.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.signalforge import store
from backend.app.signalforge.catalog import build_catalog
from backend.app.signalforge.expand import expand_catalog
from backend.app.signalforge.openscenario import export_scenario
from backend.app.signalforge.schema import ConcreteScenario
from backend.app.signalforge.sim import annotate_scenario


def _load_from_store(limit: int, family: str | None) -> list[ConcreteScenario]:
    summaries = store.list_summaries(family=family, limit=limit)
    scenarios = []
    for summary in summaries:
        scenario = store.load_concrete(summary.id)
        if scenario is not None:
            scenarios.append(scenario)
    return scenarios


def _load_from_catalog(limit: int, family: str | None, seed: int) -> list[ConcreteScenario]:
    logicals = build_catalog()
    if family:
        logicals = [s for s in logicals if s.family.value == family]
    scenarios = expand_catalog(logicals, target_count=max(limit, len(logicals)), seed=seed)
    scenarios = scenarios[:limit]
    for scenario in scenarios:
        if scenario.metrics is None:
            annotate_scenario(scenario)
    return scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "openscenario",
        help="Output directory for the bundles",
    )
    parser.add_argument("--limit", type=int, default=100, help="How many scenarios to export")
    parser.add_argument("--family", default=None, help="Only export this scenario family")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--from-catalog",
        action="store_true",
        help="Expand the logical catalog instead of reading the generated store",
    )
    parser.add_argument(
        "--trajectory-mode",
        action="store_true",
        help=(
            "Drive every actor from its simulated polyline. Reproduces the "
            "simulated motion exactly, at the cost of readability."
        ),
    )
    parser.add_argument(
        "--reference-driver",
        action="store_true",
        help="Script the R157 competent-driver braking response for the ego",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=1,
        help="Emit every Nth trajectory vertex (1 = every simulated step)",
    )
    args = parser.parse_args()

    if args.from_catalog:
        scenarios = _load_from_catalog(args.limit, args.family, args.seed)
    else:
        scenarios = _load_from_store(args.limit, args.family)
        if not scenarios:
            print(
                "No scenarios in the store. Run scripts/generate_signalforge.py first, "
                "or pass --from-catalog.",
                file=sys.stderr,
            )
            return 1

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for scenario in scenarios:
        bundle = export_scenario(
            scenario,
            trajectory_mode=args.trajectory_mode,
            reference_driver=args.reference_driver,
            trajectory_stride=args.stride,
        )
        xosc_path, xodr_path = bundle.write(args.out)
        manifest.append(
            {
                "scenario_id": scenario.id,
                "logical_id": scenario.logical_id,
                "family": scenario.family.value,
                "xosc": xosc_path.name,
                "xodr": xodr_path.name,
                "provenance": scenario.provenance.model_dump(mode="json"),
                "difficulty": scenario.difficulty.value if scenario.difficulty else None,
                "actor_actions": bundle.actor_actions,
            }
        )

    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    total_bytes = sum(p.stat().st_size for p in args.out.glob("*.xosc"))
    print(f"Exported {len(manifest)} scenarios to {args.out}")
    print(f"  manifest: {manifest_path}")
    print(f"  mode:     {'trajectory' if args.trajectory_mode else 'semantic'}")
    print(f"  .xosc total size: {total_bytes / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
