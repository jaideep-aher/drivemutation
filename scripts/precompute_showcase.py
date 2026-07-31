#!/usr/bin/env python3
"""Precompute showcase lidar renders for a subset of scenarios."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.signalforge.render import render_scenario
from backend.app.signalforge import store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--beams", type=int, default=16)
    parser.add_argument("--azimuth", type=int, default=128)
    parser.add_argument("--max-frames", type=int, default=12)
    args = parser.parse_args()

    index = store.load_index()
    if not index:
        print("No concrete scenarios. Run generate_signalforge.py first.")
        sys.exit(1)

    # Prefer diversity across families and hard scenarios
    by_family: dict[str, list] = {}
    for e in index:
        by_family.setdefault(e["family"], []).append(e)

    selected = []
    families = list(by_family.keys())
    i = 0
    while len(selected) < args.count and families:
        fam = families[i % len(families)]
        bucket = by_family[fam]
        if bucket:
            # Prefer harder ones
            bucket.sort(key=lambda e: (e.get("difficulty") != "hard", e.get("min_ttc_s") or 99))
            selected.append(bucket.pop(0))
        else:
            families.remove(fam)
            continue
        i += 1

    print(f"Precomputing {len(selected)} showcase scenarios...")
    for j, e in enumerate(selected):
        sc = store.load_concrete(e["id"])
        if not sc:
            continue
        frames = render_scenario(
            sc,
            max_frames=args.max_frames,
            lidar_beams=args.beams,
            lidar_azimuth=args.azimuth,
            degrade=True,
        )
        store.save_showcase_frame(sc.id, [f.model_dump(mode="json") for f in frames])
        print(f"  [{j+1}/{len(selected)}] {sc.id} frames={len(frames)} pts={len(frames[0].xyz)//3 if frames else 0}")

    # Write showcase index
    showcase_ids = [e["id"] for e in selected]
    (store.SHOWCASE_DIR / "index.json").write_text(
        __import__("json").dumps(showcase_ids, indent=2)
    )
    print("Done.")


if __name__ == "__main__":
    main()
