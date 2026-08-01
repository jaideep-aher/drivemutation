"""The SUT-neutral reference driver that criticality is measured against.

A scenario benchmark needs a yardstick, and the choice of yardstick decides what
the benchmark is worth.  Tuning scenarios until they break one particular
planner produces a benchmark that measures that planner and nothing else.  So
criticality here is defined against a *reference driver* — a fixed, published,
stack-independent model of what a competent human driver would have managed.

The model follows the competent-driver construct in UNECE R157 (Annex 4,
Appendix 3): the driver perceives a risk, takes a fixed risk-perception plus
reaction time to respond, and then brakes at a bounded deceleration.  A scenario
the reference driver cannot survive is unavoidable, and says nothing about a
system under test.  A scenario it survives only just is where the information is.

One correction relative to the original inline implementation is worth calling
out, because it changes published metrics.  The reaction delay used to be
measured from the *start of the scenario*, so a hazard that first appeared at
t = 3 s was reacted to instantly — the delay had already elapsed. The delay is
now measured from the moment the hazard becomes perceptible, which is what R157
describes and what makes a criticality search meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass

#: UNECE R157 Annex 4 App.3 risk perception time.
R157_RISK_PERCEPTION_S = 0.4
#: UNECE R157 Annex 4 App.3 reaction time following risk perception.
R157_REACTION_S = 0.75
#: Bounded braking effort for the competent driver, in m/s^2.
R157_MAX_DECEL_MPS2 = 7.0
#: Time-to-collision at which a hazard is treated as perceptible.
DEFAULT_PERCEPTION_TTC_S = 2.5


@dataclass(frozen=True)
class ReferenceDriver:
    """A competent driver, defined independently of any system under test.

    Every parameter is published or explicitly chosen, so a reader can check the
    yardstick rather than take it on trust.
    """

    risk_perception_s: float = R157_RISK_PERCEPTION_S
    reaction_s: float = R157_REACTION_S
    max_decel_mps2: float = R157_MAX_DECEL_MPS2
    perception_ttc_s: float = DEFAULT_PERCEPTION_TTC_S

    @property
    def total_delay_s(self) -> float:
        """Time from a hazard becoming perceptible to braking starting."""
        return self.risk_perception_s + self.reaction_s

    def brakes_at(self, hazard_visible_since: float | None, now: float) -> bool:
        """Whether the driver is braking at time ``now``.

        ``hazard_visible_since`` is when the hazard first became perceptible, or
        None if it never has.
        """
        if hazard_visible_since is None:
            return False
        return now >= hazard_visible_since + self.total_delay_s

    def perceives(self, ttc: float | None) -> bool:
        """Whether a hazard at this time-to-collision is perceptible as a risk."""
        return ttc is not None and ttc < self.perception_ttc_s

    @classmethod
    def from_odd(cls, odd: dict) -> "ReferenceDriver":
        """Build a driver, letting a scenario's ODD override the defaults.

        Regulatory scenarios carry their own risk-perception and reaction values
        in ``r157_params``, which flow into the concrete scenario's ODD.
        """
        return cls(
            risk_perception_s=float(odd.get("risk_perception_s", R157_RISK_PERCEPTION_S)),
            reaction_s=float(odd.get("reaction_s", R157_REACTION_S)),
            max_decel_mps2=float(odd.get("reference_max_decel_mps2", R157_MAX_DECEL_MPS2)),
            perception_ttc_s=float(odd.get("perception_ttc_s", DEFAULT_PERCEPTION_TTC_S)),
        )

    def describe(self) -> dict[str, float | str]:
        return {
            "model": "UNECE R157 Annex 4 App.3 competent driver",
            "risk_perception_s": self.risk_perception_s,
            "reaction_s": self.reaction_s,
            "total_delay_s": self.total_delay_s,
            "max_decel_mps2": self.max_decel_mps2,
            "perception_ttc_s": self.perception_ttc_s,
        }
