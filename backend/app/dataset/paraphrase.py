"""Deterministic NL paraphrase templates (optional Claude if ANTHROPIC_API_KEY set)."""

from __future__ import annotations

import os
from pathlib import Path

from backend.app.dataset.schemas import ScenarioFamily

GOAL_TEMPLATES: dict[ScenarioFamily, list[str]] = {
    ScenarioFamily.OCCLUDED_PEDESTRIAN: [
        "Activate an occluded pedestrian crossing that emerges from behind cover when ego approaches (variant {variant}).",
        "Mutate the scene so a hidden pedestrian steps into ego's path near the occluder (variant {variant}).",
        "Create a counterfactual where a pedestrian is revealed late from occlusion and crosses (variant {variant}).",
    ],
    ScenarioFamily.OCCLUDED_CYCLIST: [
        "Introduce an occluded cyclist that crosses the ego lane after being hidden (variant {variant}).",
        "Mutate so a cyclist emerges from behind a parked vehicle into ego's path (variant {variant}).",
        "Build a late-reveal cyclist crossing hazard for regression testing (variant {variant}).",
    ],
    ScenarioFamily.AGGRESSIVE_CUT_IN: [
        "Add an aggressive cut-in from an adjacent vehicle at short range (variant {variant}).",
        "Mutate the scene so a neighboring vehicle cuts into ego's lane abruptly (variant {variant}).",
        "Create a close-range lateral cut-in conflict against ego (variant {variant}).",
    ],
    ScenarioFamily.MERGE: [
        "Create a merge conflict where another vehicle squeezes into ego's lane under pressure (variant {variant}).",
        "Mutate to force a merge-into-ego-lane hazard with limited gap (variant {variant}).",
        "Add a merging vehicle that competes for ego's lane space (variant {variant}).",
    ],
    ScenarioFamily.UNPROTECTED_LEFT: [
        "Set up an unprotected left conflict with oncoming or cross traffic (variant {variant}).",
        "Mutate the intersection so ego faces a left-turn conflict hazard (variant {variant}).",
        "Create a four-way unprotected left testing goal with conflicting traffic (variant {variant}).",
    ],
    ScenarioFamily.CONSTRUCTION_ZONE: [
        "Introduce a construction-zone blockage that forces a hazardous lane interaction (variant {variant}).",
        "Mutate the scene with a stationary construction blocker in ego's path (variant {variant}).",
        "Create a construction closure hazard requiring evasive assessment (variant {variant}).",
    ],
    ScenarioFamily.EMERGENCY_VEHICLE: [
        "Add an emergency vehicle approaching that creates a right-of-way hazard (variant {variant}).",
        "Mutate so an emergency responder vehicle closes on ego's path (variant {variant}).",
        "Create an emergency-vehicle approach conflict for safety oracle testing (variant {variant}).",
    ],
    ScenarioFamily.WRONG_WAY_VEHICLE: [
        "Introduce a wrong-way vehicle traveling against traffic in ego's lane (variant {variant}).",
        "Mutate the scene with an oncoming wrong-way actor on the ego path (variant {variant}).",
        "Create a head-on wrong-way vehicle hazard (variant {variant}).",
    ],
}

IMPOSSIBLE_TEMPLATES = [
    "Make the {actor} teleport 500 meters instantly with infinite acceleration (impossible request {variant}).",
    "Remove the ego vehicle entirely and still evaluate ego safety oracles (contradiction {variant}).",
    "Set pedestrian speed to 200 m/s while keeping the scene physically valid (impossible {variant}).",
    "Require the parked occluder to fly above the roadway at 80 m/s (impossible {variant}).",
    "Change gravity and elevation so actors leave the 2D plane (out of scope {variant}).",
    "Make ego both parked and reach a distant ego-distance trigger without motion (contradiction {variant}).",
]


def _load_dotenv_local() -> None:
    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env.local"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def anthropic_available() -> bool:
    _load_dotenv_local()
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def paraphrase_goal(
    family: ScenarioFamily,
    variant: int,
    *,
    impossible: bool = False,
    actor_label: str = "actor",
) -> str:
    if impossible:
        base = IMPOSSIBLE_TEMPLATES[variant % len(IMPOSSIBLE_TEMPLATES)].format(
            actor=actor_label, variant=variant
        )
    else:
        templates = GOAL_TEMPLATES[family]
        base = templates[variant % len(templates)].format(variant=variant)

    if not anthropic_available():
        return base
    try:
        return _claude_paraphrase(base)
    except Exception:
        return base


def _claude_paraphrase(text: str) -> str:
    import json
    import urllib.request

    _load_dotenv_local()
    api_key = os.environ["ANTHROPIC_API_KEY"].strip()
    payload = {
        "model": "claude-3-5-haiku-latest",
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Paraphrase the following autonomous-driving test goal in one or two "
                    "sentences. Keep the same meaning. Do not invent numeric values, "
                    "actor ids, lane ids, or mutation operations. Return plain text only.\n\n"
                    f"{text}"
                ),
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    parts = body.get("content") or []
    text_out = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
    if not text_out:
        raise RuntimeError("empty Claude paraphrase")
    return text_out
