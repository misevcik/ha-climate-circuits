"""Hot water circulation hysteresis."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.circulation import (
    CirculationReason as R,
    circulation_decision,
)


@pytest.mark.parametrize(
    ("temperature", "running", "on", "reason"),
    [
        (35.9, False, True, R.COLD),
        (35.9, True, True, R.COLD),
        (36.5, True, True, R.WARMING),
        (36.5, False, False, R.WAITING),
        (36.0, False, False, R.WAITING),
        (37.0, True, False, R.REACHED),
        (40.0, False, False, R.REACHED),
        (None, True, False, R.NO_SENSOR),
    ],
)
def test_hysteresis(temperature, running, on, reason) -> None:
    decision = circulation_decision(temperature, 37.0, 1.0, running, enabled=True)
    assert (decision.on, decision.reason) == (on, reason)
    assert (decision.on_below, decision.off_at) == (36.0, 37.0)


def test_disabled_wins() -> None:
    decision = circulation_decision(20.0, 37.0, 1.0, running=True, enabled=False)
    assert (decision.on, decision.reason) == (False, R.DISABLED)
