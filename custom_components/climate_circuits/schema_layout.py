"""What the schema card shows: the entities of every source, circuit and the hot water.

The card reads this from the mode sensor, so it needs no configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .activity import entity_id_for

if TYPE_CHECKING:
    from .house import House


def schema_layout(house: House) -> dict[str, Any]:
    """Which entity shows what, for the schema card: it needs no configuration."""
    hass, entry_id = house.hass, house.entry.entry_id

    def find(platform: str, owner: str, key: str) -> str | None:
        return entity_id_for(hass, platform, f"{owner}_{key}")

    circuits = []
    for c in house.circuits.values():
        source = c.source()
        circuits.append(
            {
                "name": c.name,
                "source": source.id if source else None,
                "state": find("sensor", c.id, "state"),
                "target": find("sensor", c.id, "target_water_temperature"),
                "zones": find("sensor", c.id, "calling_zones"),
                "demand": find("binary_sensor", c.id, "demand"),
                "pump": find("binary_sensor", c.id, "pump"),
                "mixer": find("sensor", c.id, "mixer_position"),
                "mixer_state": find("sensor", c.id, "mixer_state"),
                "supply": c.settings.supply_sensor,
                "control": find("switch", c.id, "circuit_control"),
            }
        )
    hot_water = None
    if hw := house.hot_water:
        hot_water = {
            "state": find("sensor", hw.id, "circulation"),
            "temperature": find("sensor", hw.id, "circulation_temperature"),
            "threshold": find("number", hw.id, "circulation_threshold"),
            "delta": find("number", hw.id, "circulation_delta"),
            "enabled": find("switch", hw.id, "circulation_enabled"),
            "tank": hw.settings.tank_sensor,
            "tank_setpoint": hw.settings.tank_setpoint,
            "name": hw.settings.tank_name,
        }
    return {
        "mode": find("sensor", entry_id, "mode"),
        "control": find("switch", entry_id, "control_equipment"),
        "hot_water": hot_water,
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "temperature": find("sensor", s.id, "source_temperature"),
                "setpoint": find("sensor", s.id, "source_setpoint"),
                "setpoint_control": find("switch", s.id, "setpoint_control"),
                "margin": find("number", s.id, "setpoint_margin"),
                "margin_mode": find("select", s.id, "margin_mode"),
                "hot_water_heating": find("binary_sensor", s.id, "hot_water_heating"),
                "heater": {
                    "name": s.settings.heater_name,
                    "supply": s.settings.heater_supply,
                    "return": s.settings.heater_return,
                }
                if s.settings.heater_supply or s.settings.heater_return
                else None,
            }
            for s in house.sources.values()
        ],
        "circuits": circuits,
    }
