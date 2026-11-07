"""What a heat source should be set to: the warmest water a heating circuit wants, plus margin
(reserve + the tank's drop, measured by tank_drop).

Changed rarely and only by a whole step, so a heat pump is not driven by every small change of
the weather curve. Without demand the setting is left as it is.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
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


def tank_drop(samples: Sequence[float], share: float = 0.9, least: int = 30) -> float | None:
    """How much colder than the setting the water at the mixers gets, near its worst.

    samples: setting − water at the mixers, one a minute; the share-th percentile, so the bottom
    of the heat pump's cycles counts but a single odd reading does not. None with fewer than
    least samples.
    """
    if len(samples) < least:
        return None
    ordered = sorted(samples)
    # Never below 0: water warmer than the setting (another heat source) must not lower it.
    return max(round(ordered[max(math.ceil(share * len(ordered)) - 1, 0)], 1), 0.0)
