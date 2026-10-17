"""Circuit settings from the subentry data, also as older versions stored it."""

from __future__ import annotations

from custom_components.climate_circuits.settings import CircuitSettings


def test_mixer_values_from_before_the_mixer_section() -> None:
    data = {"name": "F1", "outputs": {"pump": "switch.p", "travel": 90, "settle": 120}}
    mixer = CircuitSettings.from_data(data).mixer
    assert (mixer.travel, mixer.settle, mixer.hysteresis) == (90, 120, 0.5)
    assert mixer.compensate and mixer.min_source_gap == 3.0


def test_mixer_section_wins() -> None:
    data = {
        "name": "F1",
        "outputs": {"travel": 90},
        "mixer": {"travel": 140, "gain": 2.5, "source_compensation": False, "max_step": 10},
    }
    mixer = CircuitSettings.from_data(data).mixer
    assert (mixer.travel, mixer.gain, mixer.compensate, mixer.max_step) == (140, 2.5, False, 10)
