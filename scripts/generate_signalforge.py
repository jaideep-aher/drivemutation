#!/usr/bin/env python3
"""Generate SignalForge catalog, expand concrete scenarios, run SGO ingest, annotate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.signalforge.catalog import build_catalog
from backend.app.signalforge.expand import catalog_coverage, expand_catalog
from backend.app.signalforge.sgo import run_sgo_pipeline
from backend.app.signalforge.sim import annotate_scenario
from backend.app.signalforge import store


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SignalForge scenario dataset")
    parser.add_argument("--target", type=int, default=5000, help="Target concrete scenarios")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-sgo", action="store_true")
    parser.add_argument("--skip-sim", action="store_true", help="Skip criticality annotation (faster)")
    args = parser.parse_args()

    store.ensure_dirs()

    print("[1/4] Building logical catalog...")
    logicals = build_catalog()
    store.save_catalog(logicals)
    print(f"  saved {len(logicals)} logical scenarios -> {store.CATALOG_PATH}")

    if not args.skip_sgo:
        print("[2/4] Ingesting NHTSA SGO / seed incidents...")
        result = run_sgo_pipeline(store.DATA)
        store.save_incidents(result["classified"])
        store.save_gaps(result["gaps"])
        store.save_family_weights(result["weights"])
        print(
            f"  source={result['source']} classified={result['n_classified']} "
            f"gaps={result['n_gaps']}"
        )
    else:
        print("[2/4] Skipping SGO ingest")

    print(f"[3/4] Expanding to ~{args.target} concrete scenarios...")
    concrete = expand_catalog(logicals, target_count=args.target, seed=args.seed)
    print(f"  expanded to {len(concrete)} feasible concrete scenarios")

    if not args.skip_sim:
        print("[4/4] Annotating criticality metrics...")
        for i, s in enumerate(concrete):
            annotate_scenario(s)
            if (i + 1) % 500 == 0:
                print(f"  annotated {i + 1}/{len(concrete)}")
        print(f"  done annotating {len(concrete)}")
    else:
        print("[4/4] Skipping sim annotation")

    n = store.save_concrete(concrete)
    print(f"Saved {n} concrete scenarios to {store.CONCRETE_DIR}")

    coverage = catalog_coverage(logicals, concrete)
    store.save_odd_coverage(coverage)
    print(
        f"Pairwise ODD coverage: {coverage['coverage_pct']}% of "
        f"{coverage['reachable_tuples']} reachable combinations "
        f"({coverage['unreachable_tuples']} ruled out by constraints)"
    )
    if not coverage["complete"]:
        print(f"  INCOMPLETE for: {coverage['incomplete_logicals']}")
    stats = store.coverage_stats(gap_count=len(store.load_gaps()))
    print(
        f"Coverage: logical={stats.total_logical} concrete={stats.total_concrete} "
        f"families={len(stats.by_family)} gaps={stats.gap_count}"
    )


if __name__ == "__main__":
    main()
