"""Config flow: the house entry, its options, and circuit and heat source subentries."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector as sel

from .const import (
    DEFAULT_COOL_CURVE,
    DEFAULT_DELTA,
    DEFAULT_EXERCISE_DAYS,
    DEFAULT_HEAT_CURVE,
    DEFAULT_HYSTERESIS,
    DEFAULT_MODE_PAUSE,
    DEFAULT_PUMP_DELAY,
    DEFAULT_PUMP_RUN_ON,
    DEFAULT_SETTLE,
    DEFAULT_THRESHOLD,
    DEFAULT_TRAVEL,
    DOMAIN,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
)
from .core.mode import FallbackKind

MODE_ENTITY_DOMAINS = [
    "climate",
    "select",
    "input_select",
    "sensor",
    "binary_sensor",
    "switch",
    "input_boolean",
]
VALUES = sel.TextSelector(sel.TextSelectorConfig(multiple=True))
TEMPERATURE_SENSOR = sel.EntitySelector(
    sel.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
RELAY = sel.EntitySelector(sel.EntitySelectorConfig(domain=["switch", "input_boolean"]))
CLIMATES = sel.EntitySelector(sel.EntitySelectorConfig(domain="climate", multiple=True))


def _number(minimum: float, maximum: float, step: float, unit: str = "") -> sel.NumberSelector:
    config = sel.NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=sel.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return sel.NumberSelector(config)


def _select(options: list[str], key: str, multiple: bool = False) -> sel.SelectSelector:
    return sel.SelectSelector(
        sel.SelectSelectorConfig(options=options, multiple=multiple, translation_key=key)
    )


def _section(fields: dict, collapsed: bool = True) -> section:
    return section(vol.Schema(fields), {"collapsed": collapsed})


DEGREES = _number(-30, 90, 0.5, "°C")
CURVE_SELECTORS = {
    "room": DEGREES,
    "design_outdoor": DEGREES,
    "design_supply": DEGREES,
    "exponent": _number(1, 2, 0.05),
    "slope": _number(0, 5, 0.05),
    "minimum": DEGREES,
    "maximum": DEGREES,
    "correction": _number(-10, 10, 0.5, "°C"),
}

HOUSE_SCHEMA = vol.Schema(
    {
        vol.Required("mode"): _section(
            {
                vol.Required("capabilities", default=["heat"]): _select(
                    ["heat", "cool"], "capabilities", multiple=True
                ),
                vol.Optional("mode_entity"): sel.EntitySelector(
                    sel.EntitySelectorConfig(domain=MODE_ENTITY_DOMAINS)
                ),
                vol.Optional("heat_values"): VALUES,
                vol.Optional("cool_values"): VALUES,
                vol.Optional("off_values"): VALUES,
            },
            collapsed=False,
        ),
        vol.Required("fallback"): _section(
            {
                vol.Required("kind", default=FallbackKind.NONE.value): _select(
                    [k.value for k in FallbackKind], "kind"
                ),
                vol.Optional("sensor"): TEMPERATURE_SENSOR,
                vol.Optional("heat_threshold"): DEGREES,
                vol.Optional("cool_threshold"): DEGREES,
            }
        ),
        vol.Required("weather"): _section(
            {vol.Optional("outdoor_sensor"): TEMPERATURE_SENSOR}, collapsed=False
        ),
        vol.Optional("zone_control"): _section(
            {
                vol.Required("switch_zones", default=True): sel.BooleanSelector(),
            }
        ),
        vol.Optional("hot_water"): _section(
            {
                vol.Optional("circulation_sensor"): TEMPERATURE_SENSOR,
                vol.Optional("circulation_pump"): RELAY,
                vol.Required("threshold", default=DEFAULT_THRESHOLD): _number(20, 60, 0.5, "°C"),
                vol.Required("delta", default=DEFAULT_DELTA): _number(0.5, 10, 0.5, "°C"),
            }
        ),
        vol.Optional("protection"): _section(
            {
                vol.Required("mode_pause", default=DEFAULT_MODE_PAUSE): _number(0, 240, 5, "min"),
                vol.Required("exercise_days", default=DEFAULT_EXERCISE_DAYS): _number(
                    0, 60, 1, "d"
                ),
                vol.Required("home_mixers_on_start", default=False): sel.BooleanSelector(),
            }
        ),
        vol.Required("display"): _section(
            {
                vol.Optional("info_sensors"): sel.EntitySelector(
                    sel.EntitySelectorConfig(domain="sensor", multiple=True)
                )
            }
        ),
    }
)


def circuit_schema(sources: dict[str, str]) -> vol.Schema:
    """The circuit form; sources maps the house's heat source subentries to their names."""
    source = (
        {
            vol.Optional("source"): sel.SelectSelector(
                sel.SelectSelectorConfig(
                    options=[{"value": k, "label": v} for k, v in sources.items()]
                )
            )
        }
        if sources
        else {}
    )
    return vol.Schema(
        {
            **CIRCUIT_SCHEMA.schema,
            vol.Required("outputs"): _section({**source, **OUTPUTS_SCHEMA.schema}),
        }
    )


OUTPUTS_SCHEMA = vol.Schema(
    {
        vol.Optional("pump"): RELAY,
        vol.Optional("mixer_open"): RELAY,
        vol.Optional("mixer_close"): RELAY,
        vol.Optional("supply_sensor"): TEMPERATURE_SENSOR,
        vol.Optional("mixer_position"): sel.EntitySelector(
            sel.EntitySelectorConfig(domain="cover")
        ),
        vol.Required("pump_delay", default=DEFAULT_PUMP_DELAY): _number(0, 900, 10, "s"),
        vol.Required("pump_run_on", default=DEFAULT_PUMP_RUN_ON): _number(0, 900, 10, "s"),
        vol.Required("travel", default=DEFAULT_TRAVEL): _number(10, 600, 1, "s"),
        vol.Required("hysteresis", default=DEFAULT_HYSTERESIS): _number(0.1, 5, 0.1, "°C"),
        vol.Required("settle", default=DEFAULT_SETTLE): _number(30, 600, 10, "s"),
    }
)

SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): sel.TextSelector(),
        vol.Optional("temperature_sensor"): TEMPERATURE_SENSOR,
        vol.Optional("setpoint_entity"): sel.EntitySelector(
            sel.EntitySelectorConfig(domain=["climate", "number", "input_number", "sensor"])
        ),
    }
)

CIRCUIT_SCHEMA = vol.Schema(
    {
        vol.Required("name"): sel.TextSelector(),
        vol.Required("zones"): _section(
            {
                vol.Optional("heating_zones"): CLIMATES,
                vol.Optional("cooling_zones"): CLIMATES,
                vol.Optional("humidity_sensors"): sel.EntitySelector(
                    sel.EntitySelectorConfig(
                        domain="sensor", device_class="humidity", multiple=True
                    )
                ),
            },
            collapsed=False,
        ),
        **{
            vol.Required(key): _section(
                {vol.Required(k, default=v): CURVE_SELECTORS[k] for k, v in defaults.items()}
            )
            for key, defaults in (
                ("heat_curve", DEFAULT_HEAT_CURVE),
                ("cool_curve", DEFAULT_COOL_CURVE),
            )
        },
    }
)


def _validate_house(data: dict[str, Any]) -> dict[str, str]:
    fallback, hot_water = data["fallback"], data.get("hot_water", {})
    if not data["mode"].get("capabilities"):
        return {"base": "no_capabilities"}
    if fallback["kind"] != FallbackKind.NONE and not fallback.get("sensor"):
        return {"base": "fallback_sensor_required"}
    if bool(hot_water.get("circulation_sensor")) != bool(hot_water.get("circulation_pump")):
        return {"base": "circulation_needs_sensor_and_pump"}
    return {}


def _validate_circuit(data: dict[str, Any]) -> dict[str, str]:
    heat, outputs = data["heat_curve"], data["outputs"]
    mixer = [outputs.get("mixer_open"), outputs.get("mixer_close")]
    if any(data[k]["minimum"] > data[k]["maximum"] for k in ("heat_curve", "cool_curve")):
        return {"base": "curve_min_above_max"}
    if heat.get("design_outdoor", -15) >= heat["room"]:
        return {"base": "design_outdoor_above_room"}
    if any(mixer) and not all(mixer):
        return {"base": "mixer_needs_both_relays"}
    if all(mixer) and mixer[0] == mixer[1]:
        return {"base": "mixer_relays_same"}
    if all(mixer) and not outputs.get("supply_sensor"):
        return {"base": "mixer_needs_supply_sensor"}
    return {}


class ClimateCircuitsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ClimateCircuitsOptionsFlow:
        return ClimateCircuitsOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_TYPE_CIRCUIT: CircuitSubentryFlow,
            SUBENTRY_TYPE_SOURCE: SourceSubentryFlow,
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = _validate_house(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title="Climate Circuits", data={}, options=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(HOUSE_SCHEMA, user_input or {}),
            errors=errors,
        )


class ClimateCircuitsOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = _validate_house(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                HOUSE_SCHEMA, user_input or self.config_entry.options
            ),
            errors=errors,
        )


class CircuitSubentryFlow(ConfigSubentryFlow):
    @property
    def _schema(self) -> vol.Schema:
        entry = self._get_entry()
        sources = {
            s.subentry_id: s.title for s in entry.get_subentries_of_type(SUBENTRY_TYPE_SOURCE)
        }
        return circuit_schema(sources)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors = _validate_circuit(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title=user_input["name"], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(self._schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors = _validate_circuit(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input["name"], data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema, user_input or dict(subentry.data)
            ),
            errors=errors,
        )


class SourceSubentryFlow(ConfigSubentryFlow):
    """A buffer tank, boiler or heat pump the circuits take their water from."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=user_input["name"], data=user_input)
        return self.async_show_form(step_id="user", data_schema=SOURCE_SCHEMA)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input["name"], data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SOURCE_SCHEMA, dict(subentry.data)),
        )
