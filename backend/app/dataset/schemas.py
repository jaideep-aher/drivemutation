"""Stage 2 dataset schemas  -  examples, rejections, composition keys."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from backend.app.schemas.common import Assumption, StrictModel, Unknown
from backend.app.schemas.mutations import MutationSpec
from backend.app.schemas.oracles import OracleResult
from backend.app.schemas.scenario import ScenarioSpec, ValidationIssue


class ScenarioFamily(str, Enum):
    OCCLUDED_PEDESTRIAN = "occluded_pedestrian"
    OCCLUDED_CYCLIST = "occluded_cyclist"
    AGGRESSIVE_CUT_IN = "aggressive_cut_in"
    MERGE = "merge"
    UNPROTECTED_LEFT = "unprotected_left"
    CONSTRUCTION_ZONE = "construction_zone"
    EMERGENCY_VEHICLE = "emergency_vehicle"
    WRONG_WAY_VEHICLE = "wrong_way_vehicle"


class RoadLayoutKind(str, Enum):
    STRAIGHT_DUAL = "straight_dual"
    STRAIGHT_TRIPLE = "straight_triple"
    FOUR_WAY = "four_way"


class ActorKind(str, Enum):
    PEDESTRIAN = "pedestrian"
    CYCLIST = "cyclist"
    PASSENGER_VEHICLE = "passenger_vehicle"
    EMERGENCY_VEHICLE = "emergency_vehicle"


class TriggerKind(str, Enum):
    TIME = "time"
    EGO_DISTANCE = "ego_distance"
    EGO_ENTER_REGION = "ego_enter_region"
    NONE = "none"


class HazardKind(str, Enum):
    OCCLUDED_CROSSING_PED = "occluded_crossing_ped"
    OCCLUDED_CROSSING_CYCLIST = "occluded_crossing_cyclist"
    CUT_IN = "cut_in"
    MERGE_CONFLICT = "merge_conflict"
    LEFT_TURN_CONFLICT = "left_turn_conflict"
    CONSTRUCTION_BLOCK = "construction_block"
    EMERGENCY_APPROACH = "emergency_approach"
    WRONG_WAY = "wrong_way"


FAMILY_TO_HAZARD: dict[ScenarioFamily, HazardKind] = {
    ScenarioFamily.OCCLUDED_PEDESTRIAN: HazardKind.OCCLUDED_CROSSING_PED,
    ScenarioFamily.OCCLUDED_CYCLIST: HazardKind.OCCLUDED_CROSSING_CYCLIST,
    ScenarioFamily.AGGRESSIVE_CUT_IN: HazardKind.CUT_IN,
    ScenarioFamily.MERGE: HazardKind.MERGE_CONFLICT,
    ScenarioFamily.UNPROTECTED_LEFT: HazardKind.LEFT_TURN_CONFLICT,
    ScenarioFamily.CONSTRUCTION_ZONE: HazardKind.CONSTRUCTION_BLOCK,
    ScenarioFamily.EMERGENCY_VEHICLE: HazardKind.EMERGENCY_APPROACH,
    ScenarioFamily.WRONG_WAY_VEHICLE: HazardKind.WRONG_WAY,
}


class CompositionKey(StrictModel):
    road_layout: RoadLayoutKind
    actor: ActorKind
    trigger: TriggerKind
    hazard: HazardKind

    def fingerprint(self) -> str:
        return "|".join(
            [
                self.road_layout.value,
                self.actor.value,
                self.trigger.value,
                self.hazard.value,
            ]
        )


class TargetKind(str, Enum):
    MUTATION = "mutation"
    REJECTION = "rejection"


class RejectionReason(StrictModel):
    code: str
    message: str


class RejectionTarget(StrictModel):
    status: Literal["rejected"] = "rejected"
    reasons: list[RejectionReason] = Field(..., min_length=1)
    notes: str = ""


class MutationTarget(StrictModel):
    status: Literal["accepted"] = "accepted"
    mutation: MutationSpec
    activated_hazard: HazardKind
    scenario_family: ScenarioFamily


class ExpectedValidation(StrictModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class DatasetExample(StrictModel):
    id: str
    split: Literal["train", "validation", "test"]
    scenario_family: ScenarioFamily
    composition: CompositionKey
    target_kind: TargetKind
    seed_scene: ScenarioSpec
    testing_goal: str
    canonical_target: dict[str, Any]
    expected_scenario_family: ScenarioFamily
    expected_activated_hazard: HazardKind | None = None
    expected_validation_result: ExpectedValidation
    expected_safety_oracle_results: list[OracleResult] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)
    messages: list[dict[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_messages(self) -> DatasetExample:
        if not self.messages:
            raise ValueError("messages must be populated for SFT export")
        roles = [m.get("role") for m in self.messages]
        if roles != ["system", "user", "assistant"]:
            raise ValueError("messages must be [system, user, assistant]")
        return self


SYSTEM_PROMPT = (
    "You are DriveMutation's counterfactual test compiler. "
    "Given a structured seed driving scene and a natural-language testing goal, "
    "emit ONLY a single JSON object that is either an accepted mutation specification "
    "or a structured rejection. Do not include markdown, commentary, or extra keys "
    "beyond the canonical schema. All numeric values must be physically valid SI units."
)


def build_sft_messages(
    seed_scene: ScenarioSpec,
    testing_goal: str,
    assistant_json: str,
) -> list[dict[str, str]]:
    user = (
        "Seed scene (JSON):\n"
        f"{seed_scene.model_dump_json(indent=2)}\n\n"
        f"Testing goal:\n{testing_goal}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant_json},
    ]
