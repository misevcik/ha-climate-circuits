"""What a heat source should be set to: the warmest water a heating circuit wants, plus margin.

Changed rarely and only by a whole step, so a heat pump is not driven by every small change of
the weather curve. Without demand the setting is left as it is.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetpointSettings:
    margin: float = 5.0  # °C above the warmest circuit target
    minimum: float = 30.0
    maximum: float = 55.0
    step: float = 1.0  # what the source accepts
    threshold: float = 1.0  # °C of difference worth a change
    interval: float = 900.0  # s between changes


@dataclass(frozen=True, slots=True)
class SetpointDecision:
    wanted: float | None  # None: nothing to set
    change: bool
    reason: str  # demand, wait, no_demand, not_heating
    circuit: str | None = None  # the circuit with the warmest target
    target: float | None = None


def _round_up(value: float, step: float) -> float:
    return math.ceil(value / step - 1e-9) * step if step > 0 else value


def setpoint_decision(
    *,
    heating: bool,
    targets: Mapping[str, float],
    current: float | None,
    since_change: float | None,
    settings: SetpointSettings,
) -> SetpointDecision:
    """targets: the water targets of the circuits that heat now, by circuit name."""
    if not heating:
        return SetpointDecision(None, False, "not_heating")
    if not targets:
        return SetpointDecision(None, False, "no_demand")
    circuit, target = max(targets.items(), key=lambda item: item[1])
    s = settings
    wanted = min(max(_round_up(target + s.margin, s.step), s.minimum), s.maximum)
    if current is not None and abs(wanted - current) < s.threshold - 1e-9:
        return SetpointDecision(wanted, False, "demand", circuit, target)
    if since_change is not None and since_change < s.interval:
        return SetpointDecision(wanted, False, "wait", circuit, target)
    return SetpointDecision(wanted, True, "demand", circuit, target)


@dataclass(frozen=True, slots=True)
class MarginSettings:
    """How the margin above the warmest circuit target learns from the mixers."""

    minimum: float = 3.0
    maximum: float = 15.0
    step: float = 1.0
    raise_after: float = 1800.0  # s between raises: the tank needs time to heat up
    lower_after: float = 3600.0  # s of water warmer than needed before each lowering


def next_margin(
    margin: float,
    *,
    starved: bool,
    comfortable_for: float | None,
    since_change: float | None,
    settings: MarginSettings,
) -> tuple[float, str | None]:
    """The margin after this look at the mixers, and why it changed (raise, lower) or None.

    starved: a heating circuit's mixer is fully open and still below its target;
    comfortable_for: s all heating mixers have been well below fully open and at their target.
    """
    s = settings
    if starved:
        if margin < s.maximum and (since_change is None or since_change >= s.raise_after):
            return min(margin + s.step, s.maximum), "raise"
        return margin, None
    if (
        comfortable_for is not None
        and comfortable_for >= s.lower_after
        and margin > s.minimum
        and (since_change is None or since_change >= s.lower_after)
    ):
        return max(margin - s.step, s.minimum), "lower"
    return margin, None
