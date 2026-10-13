"""Activity sentences that say why the mixing valve moves or stays."""

from __future__ import annotations

from custom_components.climate_circuits.core.mixer import MixerSettings, hold_reason, regulate
from custom_components.climate_circuits.core.texts import mixer_hold_text, mixer_text

S = MixerSettings(travel=100.0, hysteresis=0.5)


def _action(**kwargs):
    args = {
        "heating": True,
        "demand": True,
        "target": 36.8,
        "supply": 35.9,
        "position": 50.0,
        "since_end_pulse": None,
        "settings": S,
    } | kwargs
    return regulate(**args)


def test_supply_below_target() -> None:
    text = mixer_text(_action(supply=35.0), "GF", "en")
    assert text == "Mixer GF: opening 7 % – supply 35.0 °C is 1.8 °C below the target 36.8 °C"
    assert "pod cieľom 36.8 °C" in mixer_text(_action(supply=35.0), "GF", "sk")


def test_source_change() -> None:
    text = mixer_text(_action(supply=36.0, source=42.3, source_ref=43.0), "GF", "en")
    assert "the source fell from 43.0 °C to 42.3 °C, keeping the supply at 36.0 °C" in text
    assert text.startswith("Mixer GF: opening")


def test_no_demand_and_dry_run() -> None:
    text = mixer_text(_action(demand=False), "F1", "en", dry_run=True)
    assert text.startswith("Mixer F1: closing from 50 % – the circuit has no demand")
    assert text.endswith("(dry run, nothing switched)")


def test_why_it_holds() -> None:
    band = hold_reason(demand=True, target=36.8, supply=36.6, position=74.0, settings=S)
    assert band[0] == "band"
    assert mixer_hold_text(*band, "GF", "en") == (
        "Mixer GF: holding 74 % – supply 36.6 °C is within ±0.5 °C of the target 36.8 °C"
    )
    heading = hold_reason(
        demand=True, target=36.8, supply=35.8, position=74.0, settings=S, trend=0.6
    )
    assert heading[0] == "heading"
    assert "(+0.6 °C/min)" in mixer_hold_text(*heading, "GF", "en")
    assert hold_reason(demand=True, target=36.8, supply=None, position=74.0, settings=S) == (
        "no_supply",
        {},
    )
    # waiting for the last move to show is not worth a line
    assert (
        hold_reason(demand=True, target=36.8, supply=35.0, position=74.0, settings=S, since_move=30)
        is None
    )
    assert hold_reason(demand=False, target=36.8, supply=35.0, position=74.0, settings=S) is None


def test_why_it_holds_for_a_cold_source() -> None:
    hold = hold_reason(
        demand=True, target=36.8, supply=34.0, position=100.0, settings=S, source=36.0
    )
    assert hold[0] == "source_weak"
    assert "the source 36.0 °C is too cold for the target 36.8 °C" in mixer_hold_text(
        *hold, "GF", "en"
    )


def test_source_set_too_low_for_the_target() -> None:
    from custom_components.climate_circuits.core.texts import source_text

    assert source_text("short", "GF", "Buffer tank", 45.0, 44.0, "en") == (
        "GF: wants 44.0 °C water, but Buffer tank is set to 45.0 °C – only 1.0 °C to spare, "
        "the supply may fall short"
    )
