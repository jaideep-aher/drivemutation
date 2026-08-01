#!/usr/bin/env python3
"""Mine real ADS incident data for scenarios the catalog does not cover.

Two independent public sources, kept separate because they measure different
things:

* **NHTSA SGO** — crashes and other reportable incidents involving ADS-equipped
  vehicles. Speaks to what actually goes wrong.
* **California DMV disengagement reports** — every handover of control during
  testing. Speaks to what an ADS met and declined to handle, which is a
  near-miss signal a crash database cannot give.

Both are classified into catalog families with the same keyword rules, and the
unmatched remainder is the gap list.

The report deliberately splits the unmatched narratives three ways rather than
calling them all gaps:

* **internal** — the takeover was caused by the vehicle's own software or
  hardware, or by test administration. No scenario catalog could address it.
* **unspecific** — the narrative says an interaction went wrong but not what the
  other road user did. Scenario-relevant, but unclassifiable from the text.
* **gap** — a road situation described with enough specificity that matches no
  catalog family. Only these are candidate new scenarios.

Collapsing those three into one number would overstate the gap count several
times over, and would bury the most interesting finding: most disengagement
reporting is too vague to mine.

    python scripts/gap_report.py --years 2023 2022
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.signalforge import store
from backend.app.signalforge.cadmv import run_cadmv_pipeline
from backend.app.signalforge.catalog import build_catalog
from backend.app.signalforge.sgo import run_sgo_pipeline


def _family_table(counts: Counter[str], total: int) -> list[dict]:
    return [
        {"family": family, "count": n, "share_pct": round(100 * n / max(total, 1), 2)}
        for family, n in counts.most_common()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        type=int,
        nargs="*",
        default=[2024, 2023, 2022],
        help="CA DMV disengagement reporting years to ingest",
    )
    parser.add_argument("--skip-sgo", action="store_true")
    parser.add_argument("--skip-cadmv", action="store_true")
    parser.add_argument("--examples", type=int, default=25, help="Gap examples to keep")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "signalforge" / "gaps" / "gap_report.json",
    )
    args = parser.parse_args()

    catalog = build_catalog()
    families = sorted({s.family.value for s in catalog})
    report: dict = {
        "catalog": {
            "logical_scenarios": len(catalog),
            "families": families,
        },
        "sources": {},
    }

    if not args.skip_sgo:
        print("Ingesting NHTSA SGO…")
        sgo = run_sgo_pipeline(store.DATA)
        counts = Counter(c["family"] for c in sgo["classified"])
        report["sources"]["nhtsa_sgo"] = {
            "description": "ADS crash and incident reports (NHTSA Standing General Order)",
            "source": sgo["source"],
            "narratives": sgo["n_classified"],
            "gaps": sgo["n_gaps"],
            "by_family": _family_table(counts, sgo["n_classified"]),
            "gap_examples": [
                {"id": g.incident_id, "narrative": g.narrative[:400]}
                for g in sgo["gaps"][: args.examples]
            ],
        }
        print(f"  {sgo['n_classified']} narratives, {sgo['n_gaps']} unmatched")

    if not args.skip_cadmv:
        print(f"Ingesting CA DMV disengagement reports {args.years}…")
        cadmv = run_cadmv_pipeline(store.DATA, years=tuple(args.years))
        counts = Counter(
            c["family"]
            for c in cadmv["classified"]
            if not c["non_scenario"] and not c["unspecific"]
        )
        total = cadmv["n_classified"]
        matched = sum(1 for c in cadmv["classified"] if c["family"] != "unknown")
        report["sources"]["ca_dmv_disengagement"] = {
            "description": (
                "AV disengagement reports filed under 13 CCR 227.46. "
                "Near-miss signal: situations an ADS met and handed back."
            ),
            "source": cadmv["source"],
            "years": cadmv["years"],
            "narratives": total,
            "matched_to_family": matched,
            "internal_non_scenario": cadmv["n_non_scenario"],
            "unspecific_narrative": cadmv["n_unspecific"],
            "gaps": cadmv["n_gaps"],
            "by_family": _family_table(counts, total),
            "gap_examples": [
                {"id": g.incident_id, "narrative": g.narrative[:400]}
                for g in cadmv["gaps"][: args.examples]
            ],
        }
        print(
            f"  {total} narratives: {matched} matched, "
            f"{cadmv['n_non_scenario']} internal, "
            f"{cadmv['n_unspecific']} too vague, {cadmv['n_gaps']} gaps"
        )

    # Families the catalog defines that neither source ever exercised. These are
    # the reverse of a gap: catalogued but unobserved in the incident record.
    observed: set[str] = set()
    for source in report["sources"].values():
        observed |= {row["family"] for row in source["by_family"] if row["count"] > 0}
    report["catalog"]["families_not_observed_in_incident_data"] = sorted(
        set(families) - observed - {"unknown"}
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    print("\n— Summary —")
    for name, source in report["sources"].items():
        print(f"{name}: {source['narratives']} narratives, {source['gaps']} candidate gaps")
    unobserved = report["catalog"]["families_not_observed_in_incident_data"]
    if unobserved:
        print(f"catalogued but never observed in incident data: {', '.join(unobserved)}")
    print(f"\nReport: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
