"""Constants for Climate Circuits. Option and subentry keys are plain strings (settings.py)."""

from typing import Final

DOMAIN: Final = "climate_circuits"
SUBENTRY_TYPE_CIRCUIT: Final = "circuit"
SUBENTRY_TYPE_SOURCE: Final = "source"
STORAGE_KEY: Final = f"{DOMAIN}.state"
STORAGE_VERSION: Final = 1
EVENT_ACTIVITY: Final = f"{DOMAIN}_activity"
SERVICE_SET_CURVE: Final = "set_curve"
FRONTEND_URL: Final = f"/{DOMAIN}_frontend"
CARD_FILE: Final = "climate-circuits-curve-card.js"

EVALUATE_INTERVAL: Final = 30  # s, also without a state change
ZONE_COMMAND_ATTEMPTS: Final = 3
ZONE_COMMAND_RETRY: Final = 30  # s
RELAY_RETRY: Final = 10  # s between repeated commands to a relay
RELAY_ATTEMPTS: Final = 3  # commands without a confirming state before it is reported
RELAY_RETRY_RESET: Final = 300  # s, then a relay that never confirmed is tried again
MIXER_HOMING_DELAY: Final = 30  # s after the start before the mixers are homed
MIXER_RUN_MARGIN: Final = 15  # s a relay may run beyond a full travel plus the end pulse
RELAY_GRACE: Final = 5  # s a relay may be unavailable before it counts as lost (board blips)
START_GRACE: Final = 90  # s after the start in which missing demand does not stop outputs
SOURCE_HEADROOM: Final = 2.0  # K a heat source should be set above a circuit's target water
HOT_WATER_GRACE: Final = (
    60  # s after the start in which a missing circulation sensor is not reported
)
EXERCISE_PUMP_SECONDS: Final = 60
DEW_POINT_MARGIN: Final = 2.0  # K

# Changed in place, without a reload (entities and the curve card write them).
CURVE_SECTIONS: Final = frozenset({"heat_curve", "cool_curve"})
HOT_WATER_TUNING: Final = frozenset({"threshold", "delta"})

DEFAULT_HEAT_CURVE: Final = {
    "room": 22.0,
    "design_outdoor": -15.0,
    "design_supply": 50.0,
    "exponent": 1.3,
    "minimum": 35.0,
    "maximum": 50.0,
    "correction": 0.0,
}
DEFAULT_COOL_CURVE: Final = {
    "room": 24.0,
    "slope": 0.5,
    "minimum": 16.0,
    "maximum": 22.0,
    "correction": 0.0,
}
DEFAULT_TRAVEL: Final = 125
DEFAULT_HYSTERESIS: Final = 0.5
DEFAULT_SETTLE: Final = 150  # s after a mixer move before the next one
DEFAULT_PUMP_DELAY: Final = 180  # s, the zone valves open
DEFAULT_PUMP_RUN_ON: Final = 180  # s
DEFAULT_MODE_PAUSE: Final = 60  # min between heating and cooling
DEFAULT_EXERCISE_DAYS: Final = 7
DEFAULT_THRESHOLD: Final = 37.0
DEFAULT_DELTA: Final = 1.0

STATUSES: Final = ["dry_run", "ok"]
CIRCUIT_STATES: Final = ["heating", "cooling", "idle", "off"]
MIXER_STATES: Final = ["idle", "opening", "closing", "homing", "unknown"]
CIRCULATION_STATES: Final = ["running", "stopped", "disabled", "unavailable"]
UNKNOWN_STATES: Final = frozenset({"unavailable", "unknown"})
