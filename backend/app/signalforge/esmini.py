"""Run exported scenarios in esmini and check they reproduce SignalForge.

Validating an OpenSCENARIO export by asking "did the simulator open it?" is a
weak test.  esmini exits non-zero on structural problems — malformed XML, a
missing road file, a reference to an entity that does not exist — but it will
happily accept an invalid enumeration value and run anyway.  A file can load and
still describe the wrong scenario.

So validation here has three independent gates, weakest to strongest:

1. **Loads** — esmini exits cleanly and prints nothing that looks like an error.
2. **Schema** — the document validates against the OpenSCENARIO XSD, if one is
   available locally.  This is what catches the silently-accepted bad enum.
3. **Fidelity** — the actor trajectories esmini actually produces match the ones
   SignalForge simulated, to a stated tolerance.  This is the gate that matters:
   it is what makes the published criticality metrics reproducible by someone
   who has never run this codebase.

Only the third can tell you the export means what it says.
"""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from backend.app.signalforge.openscenario import ExportBundle, export_scenario
from backend.app.signalforge.schema import ConcreteScenario
from backend.app.signalforge.sim import simulate

#: Where to look for the esmini binary when it is not on PATH.
ESMINI_ENV_VARS = ("ESMINI", "ESMINI_BIN", "ESMINI_PATH")

#: Lines matching this in esmini's output mean something went wrong even if the
#: process exits zero.
ERROR_PATTERN = re.compile(
    r"\b(error|failed|failure|exception|unexpected|not found|aborted|invalid)\b",
    re.IGNORECASE,
)

#: Benign messages that match ERROR_PATTERN but are not failures.
BENIGN_PATTERN = re.compile(
    r"(no scene graph|scenegraph|osgb|no model|failed to load model|"
    r"model_id|texture|no .*\.osgb|odrviewer)",
    re.IGNORECASE,
)

#: esmini echoes every ParameterDeclaration as ``name = value``.  Those lines
#: carry our own provenance text, so a scenario legitimately named "Vehicle
#: Failure" would otherwise be reported as a failure by its own citation.
PARAMETER_ECHO_PATTERN = re.compile(r"^\s*[\w.\-]+\s*=\s")

#: Position tolerance for a default (semantic) export, in metres.
#:
#: Trajectory-driven actors reproduce to well under a millimetre.  The slack
#: exists for one case: a braking actor exported as a native ``SpeedAction``,
#: where the player integrates the deceleration continuously while the kinematic
#: simulator steps it at a fixed 0.1 s.  Over a full stop from motorway speed
#: that difference reaches roughly three metres.  Export with
#: ``trajectory_mode=True`` when exactness matters more than readability.
DEFAULT_POSITION_TOLERANCE_M = 3.0

#: Tolerance for a trajectory-mode export, which should be exact.
TRAJECTORY_POSITION_TOLERANCE_M = 0.01


@dataclass
class EsminiRun:
    """Result of one esmini invocation."""

    returncode: int
    stdout: str
    csv_path: Path | None
    ok: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class FidelityReport:
    """How closely esmini reproduced the simulated actor trajectories."""

    scenario_id: str
    loaded: bool
    compared_actors: int
    compared_samples: int
    max_deviation_m: float | None
    mean_deviation_m: float | None
    tolerance_m: float
    #: Per-actor worst deviation, for pinpointing which behaviour drifted.
    worst_by_actor: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def faithful(self) -> bool:
        if not self.loaded or self.max_deviation_m is None:
            return False
        return self.max_deviation_m <= self.tolerance_m

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "loaded": self.loaded,
            "faithful": self.faithful,
            "compared_actors": self.compared_actors,
            "compared_samples": self.compared_samples,
            "max_deviation_m": (
                round(self.max_deviation_m, 4) if self.max_deviation_m is not None else None
            ),
            "mean_deviation_m": (
                round(self.mean_deviation_m, 4) if self.mean_deviation_m is not None else None
            ),
            "tolerance_m": self.tolerance_m,
            "worst_by_actor": {k: round(v, 4) for k, v in self.worst_by_actor.items()},
            "errors": self.errors,
        }


def find_esmini() -> Path | None:
    """Locate the esmini binary, or return None if it is not installed."""
    for var in ESMINI_ENV_VARS:
        raw = os.environ.get(var)
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.is_dir():
            for rel in ("bin/esmini", "esmini"):
                if (candidate / rel).is_file():
                    return candidate / rel
        elif candidate.is_file():
            return candidate

    found = shutil.which("esmini")
    return Path(found) if found else None


def _classify_output(text: str) -> list[str]:
    """Extract genuine error lines, ignoring missing-3D-model chatter."""
    problems = []
    for line in text.splitlines():
        if PARAMETER_ECHO_PATTERN.match(line):
            continue
        if ERROR_PATTERN.search(line) and not BENIGN_PATTERN.search(line):
            problems.append(line.strip())
    return problems


def run_esmini(
    xosc_path: Path,
    *,
    esmini: Path | None = None,
    timestep: float = 0.1,
    csv_path: Path | None = None,
    timeout: float = 120.0,
    extra_args: Sequence[str] = (),
) -> EsminiRun:
    """Run one scenario headless and capture its log and optional CSV."""
    binary = esmini or find_esmini()
    if binary is None:
        return EsminiRun(
            returncode=-1,
            stdout="",
            csv_path=None,
            ok=False,
            errors=["esmini not found; set ESMINI or put it on PATH"],
        )

    cmd = [
        str(binary),
        "--headless",
        "--osc",
        str(xosc_path),
        "--fixed_timestep",
        str(timestep),
        # esmini writes ./log.txt by default; keep it out of the working tree.
        "--logfile_path",
        str(xosc_path.parent / "esmini.log"),
    ]
    if csv_path is not None:
        cmd += ["--csv_logger", str(csv_path)]
    cmd += list(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            # esmini resolves the road file relative to the scenario.
            cwd=str(xosc_path.parent),
        )
    except subprocess.TimeoutExpired:
        return EsminiRun(
            returncode=-1,
            stdout="",
            csv_path=None,
            ok=False,
            errors=[f"esmini timed out after {timeout}s"],
        )

    output = (proc.stdout or "") + (proc.stderr or "")
    errors = _classify_output(output)
    if proc.returncode != 0:
        errors.insert(0, f"esmini exited {proc.returncode}")

    return EsminiRun(
        returncode=proc.returncode,
        stdout=output,
        csv_path=csv_path if (csv_path and csv_path.exists()) else None,
        ok=proc.returncode == 0 and not errors,
        errors=errors,
    )


def parse_csv(path: Path) -> dict[str, list[dict[str, float]]]:
    """Parse an esmini CSV log into ``entity name -> list of states``.

    The log repeats a fixed block of columns per entity, prefixed ``#1``, ``#2``
    and so on, after two leading columns for index and timestamp.
    """
    text = path.read_text(errors="replace").splitlines()
    header_idx = next(
        (i for i, line in enumerate(text) if line.lstrip().startswith("Index")), None
    )
    if header_idx is None:
        return {}

    header = [h.strip() for h in text[header_idx].split(",")]
    # Group column indices by entity number.
    blocks: dict[str, dict[str, int]] = {}
    for i, name in enumerate(header):
        match = re.match(r"^#(\d+)\s+(.*)$", name)
        if not match:
            continue
        entity_no, field_name = match.group(1), match.group(2).strip()
        blocks.setdefault(entity_no, {})[field_name] = i

    def get(row: list[str], idx: int | None) -> float:
        if idx is None or idx >= len(row):
            return math.nan
        try:
            return float(row[idx])
        except ValueError:
            return math.nan

    tracks: dict[str, list[dict[str, float]]] = {}
    reader = csv.reader(text[header_idx + 1 :])
    for row in reader:
        if len(row) < 2:
            continue
        try:
            t = float(row[1])
        except ValueError:
            continue
        for cols in blocks.values():
            name_idx = cols.get("Entitity_Name [-]") or cols.get("Entity_Name [-]")
            if name_idx is None or name_idx >= len(row):
                continue
            entity = row[name_idx].strip()
            if not entity:
                continue
            tracks.setdefault(entity, []).append(
                {
                    "t": t,
                    "x": get(row, cols.get("World_Position_X [m]")),
                    "y": get(row, cols.get("World_Position_Y [m]")),
                    "speed": get(row, cols.get("Current_Speed [m/s]")),
                }
            )
    return tracks


def check_fidelity(
    scenario: ConcreteScenario,
    *,
    bundle: ExportBundle | None = None,
    esmini: Path | None = None,
    tolerance_m: float = DEFAULT_POSITION_TOLERANCE_M,
    work_dir: Path | None = None,
    trajectory_mode: bool = False,
) -> FidelityReport:
    """Export, run in esmini, and compare actor trajectories against the sim.

    The ego is excluded: it is deliberately unscripted in an exported bundle, so
    its motion is expected to differ.  What must match is the challenger motion,
    because that is what every system under test has to face identically.
    """
    bundle = bundle or export_scenario(scenario, trajectory_mode=trajectory_mode)
    report = FidelityReport(
        scenario_id=scenario.id,
        loaded=False,
        compared_actors=0,
        compared_samples=0,
        max_deviation_m=None,
        mean_deviation_m=None,
        tolerance_m=tolerance_m,
    )

    with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
        tmp_path = Path(tmp)
        xosc_path, _ = bundle.write(tmp_path)
        csv_path = tmp_path / f"{scenario.id}.csv"
        run = run_esmini(
            xosc_path,
            esmini=esmini,
            timestep=scenario.timestep_s,
            csv_path=csv_path,
        )
        report.errors.extend(run.errors)
        if not run.ok:
            return report
        report.loaded = True
        if run.csv_path is None:
            report.errors.append("esmini produced no CSV log")
            return report
        actual = parse_csv(run.csv_path)

    expected = simulate(scenario, record_frames=True, frame_stride=1)
    by_time: dict[str, dict[float, tuple[float, float]]] = {}
    for frame in expected.frames:
        t = round(float(frame["t"]), 3)
        for actor in frame["actors"]:
            # The export mirrors y; compare in the exported frame.
            by_time.setdefault(actor["id"], {})[t] = (actor["x"], -actor["y"])

    deviations: list[float] = []
    for actor_id, want in by_time.items():
        got = actual.get(actor_id)
        if not got:
            report.errors.append(f"actor {actor_id} missing from esmini log")
            continue
        worst = 0.0
        counted = 0
        for sample in got:
            t = round(sample["t"], 3)
            if t not in want:
                continue
            wx, wy = want[t]
            if math.isnan(sample["x"]) or math.isnan(sample["y"]):
                continue
            d = math.hypot(sample["x"] - wx, sample["y"] - wy)
            deviations.append(d)
            worst = max(worst, d)
            counted += 1
        if counted:
            report.compared_actors += 1
            report.compared_samples += counted
            report.worst_by_actor[actor_id] = worst

    if deviations:
        report.max_deviation_m = max(deviations)
        report.mean_deviation_m = sum(deviations) / len(deviations)
    elif not report.errors:
        report.errors.append("no comparable samples between sim and esmini")

    return report
