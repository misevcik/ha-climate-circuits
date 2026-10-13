# Climate Circuits

A Home Assistant integration for hydronic heating and cooling: it decides whether the house heats, cools or rests, and runs each circuit's pump and three-point mixing valve to the water temperature of its weather curve. Every decision is written to the Activity log with its reason.

Everything is set up in the UI. It works with the relays, sensors and thermostats you already have in Home Assistant.

## Features

- **House mode** – heat, cool or off, taken from a heat pump or any other entity (climate, select, sensor, switch), with a fallback sensor (buffer tank or outdoor temperature) and a manual override.
- **Weather curves** per circuit – a heating curve from the design point and the emitter exponent, a linear cooling curve that never goes below the dew point + 2 °C. A dashboard card shows the curve and lets you drag it; another one shows the whole system as a live diagram.
- **Circuit demand** from the circuit's thermostats, with the calling zones shown.
- **Circuit pumps** with a start delay (so the zone valves can open) and a run-on after heating.
- **Three-point mixing valves** – the position is calculated from the relay run times, the supply temperature is regulated in steps, the valve is homed against its end stop when the position is unknown, and the motor is protected: never both relays at once, a run-time watchdog, stray relays switched off, short relay dropouts tolerated.
- **Hot water circulation** pump with hysteresis on the return temperature.
- **Zone thermostats** – on a mode change the other mode's thermostats are turned off before the new ones are turned on.
- **Protections** – a pause between heating and cooling, a condensation guard while cooling, and exercise of idle pumps and valves.
- **Safe start** – nothing is switched until you turn on *Control equipment*; until then every decision is a dry run shown in Activity. Each circuit has its own switch as well, so circuits can go live one by one.
- **Confirmed commands** – a relay or thermostat command counts only once its state confirms it; otherwise it is repeated and reported.
- English and Slovak.

## Requirements

- Home Assistant 2026.8 or newer.
- Per circuit, whatever it has: thermostats (`climate`), a pump relay, two mixing-valve relays (open / close) and a supply temperature sensor after the valve. Relays can be any `switch` or `input_boolean`.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/misevcik/ha-climate-circuits`, type **Integration**.
2. Install **Climate Circuits** and restart Home Assistant.

### Manual

Copy `custom_components/climate_circuits` into the `custom_components` folder of your Home Assistant configuration and restart.

## Setup

1. **Settings → Devices & services → Add integration → Climate Circuits.** Set up the house: where the mode comes from, the fallback, the outdoor temperature sensor and, if you have one, the hot water circulation.
2. **Add a circuit** (*Add circuit* on the integration's page) for every pump or mixing valve: its heating and cooling thermostats, humidity sensors for cooling, both curves, the outputs (heat source, pump, mixer relays, supply sensor) and the *Mixer regulation* (valve travel time and the regulation parameters).
3. Watch the **Activity** log and the entities in **dry run**: the integration says what it would switch and why.
4. When it matches what you expect, turn on **Control equipment** and then each circuit's **Control pump and mixer** switch.

Turning *Control equipment* off at any time stops all switching; the integration goes back to a dry run.

## Entities

House:

| Entity | What it shows |
|---|---|
| `sensor.climate_circuits_mode` | heat / cool / off, with the source and reason in its attributes |
| `select.climate_circuits_mode_override` | auto / heat / cool / off |
| `sensor.climate_circuits_status` | dry run / ok |
| `switch.climate_circuits_control_equipment` | outputs are switched only while this is on |

Per circuit (`<circuit>` is the circuit's name, e.g. `f1`):

| Entity | What it shows |
|---|---|
| `binary_sensor.<circuit>_demand` | whether the circuit's zones call for heat or cold |
| `sensor.<circuit>_state` | heating / cooling / idle / off, with the reason |
| `sensor.<circuit>_calling_zones` | the thermostats that call |
| `sensor.<circuit>_target_water_temperature` | water temperature from the weather curve |
| `binary_sensor.<circuit>_pump` | the real pump relay; what the integration wants and why in its attributes |
| `sensor.<circuit>_mixer_position` | valve position in %, calculated from the relay run times |
| `sensor.<circuit>_mixer_state` | idle / opening / closing / homing / position unknown |
| `switch.<circuit>_control_pump_and_mixer` | the circuit's own switch, next to *Control equipment* |

Hot water circulation:

| Entity | What it shows |
|---|---|
| `sensor.hot_water_circulation_state` | running / stopped / disabled / unavailable, with the reason |
| `sensor.hot_water_circulation_temperature` | return temperature of the circulation loop |
| `switch.hot_water_circulation_enabled` | allows the circulation pump to run |
| `number.hot_water_circulation_threshold`, `number.hot_water_circulation_delta` | the pump starts below threshold − delta and stops at the threshold |

## Curve card

The integration registers a dashboard card that draws a circuit's weather curve with the current point; drag the points or click the values to change the curve.

```yaml
type: custom:climate-circuits-curve-card
entity: sensor.f1_target_water_temperature
```

The same change is available as an action, `climate_circuits.set_curve`, targeting a circuit's target water temperature sensor.

## Schema card

A live diagram of the heating: the heat source with its temperature and set temperature, the hot water tank with its circulation (return temperature, start and stop limits, pump), and for every circuit the mixer position (and whether it moves), the water after the mixer against its target, the pump with flowing water while it runs, and the zones calling. Warnings (relay unavailable, source not enough, dry run) show in place; the hot water tank temperature and set temperature come from two optional fields in *Hot water circulation*; click any part for its details. It needs no configuration – the integration tells the card which entities to show.

```yaml
type: custom:climate-circuits-schema-card
```

## How the mixing valve is driven

The valve has no position feedback, so the integration counts how long each relay runs, whoever switches it. Every 30 s it compares the supply temperature with the target. Outside the hysteresis it moves the valve by a step proportional to the difference (4 % per °C, 2–20 %), then waits for the settle time until the water reaches the sensor, and skips a move while the temperature is already heading for the target. When the heat source temperature changes, the valve is moved at once so the supply stays the same. All of this is set per circuit under *Mixer regulation*; without demand the valve closes. At an end stop it adds a short pulse at most every 10 minutes. The position is saved across restarts. The valve is homed (closed for one full travel) when the position is unknown: on the first start, when a move was cut off, after a relay was unavailable for more than 5 s during a move, and after 7 days without moving. A relay unavailable for longer stops the mixer and is logged in Activity, as is its return. Homing on every Home Assistant start is an option under *Protections*.

## Documentation

Design notes, the decision log and the plan are in [documents/](documents/README.md) (in Slovak).

## Development

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The decision logic lives in `custom_components/climate_circuits/core/` and has no Home Assistant imports, so it is tested on its own.

## License

MIT
