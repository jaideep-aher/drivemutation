"""Minimal OpenDRIVE road generation for exported scenarios.

Every exported scenario ships with its own road so the bundle is self-contained:
no dependency on esmini's ``resources`` directory, no scene-graph file, nothing
to install beyond a simulator.

The road is synthesised to fit the scenario rather than the other way round.
SignalForge's kinematic layer works in a Cartesian frame with the ego starting at
the origin heading +x, so the road's reference line is laid along +x and offset
laterally such that the ego's lane centre falls exactly on y = 0, with enough
lanes on each side to contain every actor for the whole run.

One deliberate simplification, stated plainly: the kinematic simulator does not
model road curvature — actors move in straight lines whatever ``road_geometry``
says.  Emitting a curved OpenDRIVE road would therefore misrepresent the
scenario, with actors flying off a bend they never drove.  So every export uses
a straight reference line and carries the declared road geometry as metadata.
Curvature belongs with the map-aware simulator in a later stage, not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

LANE_WIDTH = 3.5
#: Extra road length ahead of and behind the travelled extent.
LENGTH_MARGIN_M = 60.0
#: Shortest road worth emitting, so short scenarios still look like roads.
MIN_LENGTH_M = 250.0
#: Upper bounds on lane count.  Only entities travelling *along* the road widen
#: it, but a stray trajectory should still never turn a road into a runway.
MAX_FORWARD_LANES = 6
MAX_ONCOMING_LANES = 3


@dataclass(frozen=True)
class RoadLayout:
    """How world y maps onto OpenDRIVE lane ids for one exported scenario.

    With the reference line running along +x, OpenDRIVE's ``t`` axis points to
    the left, so a lane's centre sits at ``y_ref + t``.  Right-hand traffic puts
    same-direction lanes at negative ids (negative ``t``, below the reference
    line) and oncoming lanes at positive ids.
    """

    y_ref: float
    n_forward: int
    n_oncoming: int
    ego_lane_id: int
    x_start: float
    length: float

    def lane_center_y(self, lane_id: int) -> float:
        """World y of the centre of ``lane_id``."""
        if lane_id == 0:
            return self.y_ref
        if lane_id < 0:
            return self.y_ref - (abs(lane_id) - 0.5) * LANE_WIDTH
        return self.y_ref + (lane_id - 0.5) * LANE_WIDTH

    def lane_id_at(self, y: float) -> int:
        """Lane id whose span contains world ``y`` (clamped to the built road)."""
        t = y - self.y_ref
        if t < 0:
            idx = min(self.n_forward, max(1, math.ceil(-t / LANE_WIDTH)))
            return -idx
        idx = min(max(1, self.n_oncoming), max(1, math.ceil(t / LANE_WIDTH)))
        return idx


def plan_road(
    xs: list[float],
    forward_ys: list[float],
    oncoming_ys: list[float],
) -> RoadLayout:
    """Choose a lane layout that contains the whole scenario.

    ``forward_ys`` and ``oncoming_ys`` are every y value reached during the run by
    same-direction and opposing entities respectively, in the exported (mirrored)
    frame.  The reference line is placed directly above the forward lanes so that
    opposing traffic genuinely lands in opposing lanes.
    """
    y_max_fwd = max(forward_ys) if forward_ys else 0.0
    y_min_fwd = min(forward_ys) if forward_ys else 0.0

    # Lane centres sit at multiples of LANE_WIDTH from the ego lane at y = 0, so
    # lane k spans [(k-0.5)W, (k+0.5)W].
    lanes_above = max(0, math.ceil(y_max_fwd / LANE_WIDTH - 0.5))
    lanes_below = max(0, math.ceil(-y_min_fwd / LANE_WIDTH - 0.5))
    # Keep the ego's own lane addressable no matter how the bounds clamp.
    lanes_above = min(lanes_above, MAX_FORWARD_LANES - 1)
    lanes_below = min(lanes_below, MAX_FORWARD_LANES - 1 - lanes_above)

    n_forward = lanes_above + 1 + lanes_below
    ego_lane_id = -(lanes_above + 1)
    y_ref = (lanes_above + 0.5) * LANE_WIDTH

    if oncoming_ys:
        reach = max(oncoming_ys) - y_ref
        n_oncoming = min(MAX_ONCOMING_LANES, max(1, math.ceil(reach / LANE_WIDTH)))
    else:
        # A single opposing lane keeps the road recognisable as a two-way road
        # even when nothing drives on it.
        n_oncoming = 1

    x_min = min(xs) if xs else 0.0
    x_max = max(xs) if xs else 0.0
    x_start = x_min - LENGTH_MARGIN_M
    length = max(MIN_LENGTH_M, (x_max - x_min) + 2 * LENGTH_MARGIN_M)

    return RoadLayout(
        y_ref=y_ref,
        n_forward=n_forward,
        n_oncoming=n_oncoming,
        ego_lane_id=ego_lane_id,
        x_start=x_start,
        length=length,
    )


def _lane_xml(lane_id: int, *, outermost: bool) -> str:
    # Solid edge markings on the outermost lane, broken between driving lanes.
    mark = "solid" if outermost else "broken"
    change = "none" if outermost else "both"
    return (
        f'          <lane id="{lane_id}" type="driving" level="false">\n'
        f"            <link/>\n"
        f'            <width sOffset="0" a="{LANE_WIDTH}" b="0" c="0" d="0"/>\n'
        f'            <roadMark sOffset="0" type="{mark}" weight="standard" '
        f'color="standard" width="0.12" laneChange="{change}"/>\n'
        f"          </lane>\n"
    )


def render_opendrive(layout: RoadLayout, *, name: str = "signalforge") -> str:
    """Serialise a :class:`RoadLayout` to an OpenDRIVE document."""
    left = "".join(
        _lane_xml(i, outermost=(i == layout.n_oncoming))
        for i in range(layout.n_oncoming, 0, -1)
    )
    right = "".join(
        _lane_xml(-i, outermost=(i == layout.n_forward))
        for i in range(1, layout.n_forward + 1)
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="4" name="{name}" version="1.00" date="1970-01-01T00:00:00" north="0" south="0" east="0" west="0"/>
  <road name="{name}" length="{layout.length:.4f}" id="1" junction="-1">
    <link/>
    <planView>
      <geometry s="0" x="{layout.x_start:.4f}" y="{layout.y_ref:.4f}" hdg="0" length="{layout.length:.4f}">
        <line/>
      </geometry>
    </planView>
    <elevationProfile>
      <elevation s="0" a="0" b="0" c="0" d="0"/>
    </elevationProfile>
    <lanes>
      <laneSection s="0">
        <left>
{left}        </left>
        <center>
          <lane id="0" type="none" level="false">
            <roadMark sOffset="0" type="solid" weight="standard" color="yellow" width="0.15" laneChange="none"/>
          </lane>
        </center>
        <right>
{right}        </right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>
"""
