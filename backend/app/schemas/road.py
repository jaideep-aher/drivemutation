"""Road layout schemas — straight roads and four-way intersections."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .common import PositiveFloat, StrictModel


class RoadKind(str, Enum):
    STRAIGHT = "straight"
    FOUR_WAY_INTERSECTION = "four_way_intersection"


class Lane(StrictModel):
    """A single travel lane with centreline and boundaries in metres."""

    id: str
    center_y: float = Field(..., description="Lane centreline lateral coordinate [m]")
    width: PositiveFloat = Field(default=3.5, description="Lane width [m]")
    direction: Literal[1, -1] = Field(
        default=1, description="Travel direction along +x (1) or -x (-1)"
    )

    @property
    def left_boundary(self) -> float:
        return self.center_y + self.width / 2.0

    @property
    def right_boundary(self) -> float:
        return self.center_y - self.width / 2.0


class RoadLayout(StrictModel):
    """2D bird's-eye road geometry in SI units."""

    kind: RoadKind
    length: PositiveFloat = Field(..., description="Extent along primary axis [m]")
    lanes: list[Lane] = Field(..., min_length=1)
    intersection_center: tuple[float, float] | None = Field(
        default=None,
        description="Intersection centre (x, y) [m]; required for four-way",
    )
    intersection_size: PositiveFloat | None = Field(
        default=None,
        description="Half-width of square intersection box [m]",
    )
    cross_lane_width: PositiveFloat = Field(
        default=3.5, description="Width of crossing approach lanes [m]"
    )

    @model_validator(mode="after")
    def _check_intersection(self) -> RoadLayout:
        if self.kind == RoadKind.FOUR_WAY_INTERSECTION:
            if self.intersection_center is None or self.intersection_size is None:
                raise ValueError(
                    "four_way_intersection requires intersection_center and intersection_size"
                )
        return self
