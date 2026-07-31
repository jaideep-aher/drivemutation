"""Safety oracle schemas."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import OracleType, StrictModel


class SafetyOracle(StrictModel):
    """A pass/fail safety check evaluated over a simulation trace."""

    id: str
    type: OracleType
    threshold: float | None = Field(
        default=None,
        description="Threshold in SI units appropriate to the oracle type",
    )
    actor_id: str | None = Field(
        default=None,
        description="Optional actor scope; defaults to ego where applicable",
    )

    @model_validator(mode="after")
    def _check_threshold(self) -> SafetyOracle:
        needs_threshold = {
            OracleType.MIN_TTC,
            OracleType.MAX_ACCELERATION,
            OracleType.MAX_JERK,
        }
        if self.type in needs_threshold and self.threshold is None:
            raise ValueError(f"{self.type.value} requires threshold")
        if self.type == OracleType.MIN_TTC and self.threshold is not None:
            if self.threshold < 0:
                raise ValueError("min_ttc threshold must be >= 0 [s]")
        return self


class OracleResult(StrictModel):
    id: str
    type: OracleType
    passed: bool
    value: float | None = None
    message: str = ""
