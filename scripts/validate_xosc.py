#!/usr/bin/env python3
"""Validate exported OpenSCENARIO bundles against esmini.

Three gates, in increasing strength:

``--check load``
    esmini opens and runs the scenario without complaining.  Cheap, and the
    weakest signal: esmini will happily accept an invalid enumeration value.

``--check schema``
    The document validates against the OpenSCENARIO XSD.  Requires ``xmlschema``
    and a local copy of the schema (``--xsd``).  Skipped when unavailable.

``--check fidelity``
    esmini is run with CSV logging and the resulting actor trajectories are
    compared against SignalForge's own simulation.  This is the gate that says
    the exported file means what the catalog claims it means.

Install esmini and point ``ESMINI`` at it (either the binary or the install
directory), or put ``esmini`` on ``PATH``.
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
from backend.app.signalforge.esmini import (
    DEFAULT_POSITION_TOLERANCE_M,
    TRAJECTORY_POSITION_TOLERANCE_M,
    check_fidelity,
    find_esmini,
    run_esmini,
)
from backend.app.signalforge.expand import expand_logical
from backend.app.signalforge.openscenario import export_scenario
from backend.app.signalforge.schema import ConcreteScenario
from backend.app.signalforge.sim import annotate_scenario


def _sample_scenarios(limit: int, seed: int) -> list[ConcreteScenario]:
    """One concrete scenario per logical scenario, for broad family coverage.

    Prefers the generated store when it exists so validation runs against what
    was actually shipped, and falls back to expanding the catalog otherwise.
    """
    scenarios: list[ConcreteScenario] = []
    index = store.load_index()
    if index:
        seen: set[str] = set()
        for entry in index:
            if entry["logical_id"] in seen:
                continue
            scenario = store.load_concrete(entry["id"])
            if scenario is None:
                continue
            seen.add(entry["logical_id"])
            scenarios.append(scenario)
            if len(scenarios) >= limit:
                break
        if scenarios:
            return scenarios

    for logical in build_catalog():
        batch = expand_logical(logical, samples_per_combo=1, seed=seed, max_per_logical=1)
        if batch:
            scenarios.append(annotate_scenario(batch[0]))
        if len(scenarios) >= limit:
            break
    return scenarios


def _validate_schema(xosc: str, xsd_path: Path) -> str | None:
    """Return an error string, or None when the document validates."""
    try:
        import xmlschema
    except ImportError:
        return "xmlschema not installed"
    try:
        schema = xmlschema.XMLSchema(str(xsd_path))
        schema.validate(xosc)
    except Exception as exc:  # noqa: BLE001 - report whatever the validator says
        return str(exc).splitlines()[0][:300]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        choices=["load", "schema", "fidelity", "all"],
        default="fidelity",
        help="Which gate to run",
    )
    parser.add_argument("--limit", type=int, default=25, help="How many scenarios to check")
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument(
        "--trajectory-mode",
        action="store_true",
        help="Export every actor as a trajectory and hold it to the exact tolerance",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Position tolerance in metres (defaults to the mode's tolerance)",
    )
    parser.add_argument("--xsd", type=Path, default=None, help="OpenSCENARIO XSD for --check schema")
    parser.add_argument("--json", type=Path, default=None, help="Write a JSON report here")
    args = parser.parse_args()

    esmini = find_esmini()
    needs_esmini = args.check in ("load", "fidelity", "all")
    if needs_esmini and esmini is None:
        print(
            "esmini not found. Set ESMINI to the binary or install directory, "
            "or put esmini on PATH.",
            file=sys.stderr,
        )
        return 2
    if esmini:
        print(f"esmini: {esmini}")

    tolerance = args.tolerance
    if tolerance is None:
        tolerance = (
            TRAJECTORY_POSITION_TOLERANCE_M
            if args.trajectory_mode
            else DEFAULT_POSITION_TOLERANCE_M
        )

    scenarios = _sample_scenarios(args.limit, args.seed)
    if not scenarios:
        print("No scenarios to validate.", file=sys.stderr)
        return 1

    print(
        f"Validating {len(scenarios)} scenarios "
        f"({'trajectory' if args.trajectory_mode else 'semantic'} mode, "
        f"tolerance {tolerance} m)\n"
    )

    results = []
    failures = 0
    for scenario in scenarios:
        bundle = export_scenario(scenario, trajectory_mode=args.trajectory_mode)
        row: dict = {"scenario_id": scenario.id, "family": scenario.family.value}
        ok = True

        if args.check in ("schema", "all") and args.xsd:
            error = _validate_schema(bundle.xosc, args.xsd)
            row["schema_error"] = error
            if error and error != "xmlschema not installed":
                ok = False

        if args.check in ("load", "all"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                xosc_path, _ = bundle.write(Path(tmp))
                run = run_esmini(xosc_path, esmini=esmini, timestep=scenario.timestep_s)
            row["loaded"] = run.ok
            row["load_errors"] = run.errors[:3]
            ok = ok and run.ok

        if args.check in ("fidelity", "all"):
            report = check_fidelity(
                scenario,
                bundle=bundle,
                esmini=esmini,
                tolerance_m=tolerance,
                trajectory_mode=args.trajectory_mode,
            )
            row.update(report.as_dict())
            ok = ok and report.faithful

        results.append(row)
        if not ok:
            failures += 1
        status = "ok  " if ok else "FAIL"
        deviation = row.get("max_deviation_m")
        detail = f"max_dev={deviation:.5f} m" if isinstance(deviation, float) else ""
        print(f"  [{status}] {scenario.id:46s} {detail}")
        if not ok:
            for key in ("load_errors", "schema_error", "errors"):
                if row.get(key):
                    print(f"           {key}: {row[key]}")

    print(f"\n{len(results) - failures}/{len(results)} passed")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2) + "\n")
        print(f"report: {args.json}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
