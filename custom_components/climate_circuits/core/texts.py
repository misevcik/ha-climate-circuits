"""Activity and attribute sentences in Slovak or English."""

from __future__ import annotations

import math
from typing import Any

from .circulation import CirculationDecision
from .explain import CircuitExplanation, CircuitState, ZoneExplanation, ZoneStatus
from .mode import Mode, ModeSource
from .protect import Blocked
from .pump import PumpDecision, PumpReason

_SK = {
    "heating": "Kúri",
    "cooling": "Chladí",
    "no_heat": "Nekúri",
    "no_cool": "Nechladí",
    "circuit_off": "Vypnuté",
    "house_off": "režim domu je vypnutý",
    "no_zones": "okruh nemá zóny pre tento režim, beží s režimom domu",
    "zones_of": "{n} z {total} zón",
    "nobody": "žiadna zóna nepožaduje {what}",
    "what_heat": "teplo",
    "what_cool": "chladenie",
    "verb_heat": "kúri",
    "verb_cool": "chladí",
    "zone_calling": "{verb} {current} → {target}",
    "zone_satisfied": "teplota dosiahnutá {current} / {target}",
    "zone_waiting": "čaká v tolerancii termostatu {current} / {target}",
    "zone_off": "termostat vypnutý",
    "zone_unavailable": "nedostupný",
    "count_satisfied": "{n} má teplotu",
    "count_waiting": "{n} čaká v tolerancii",
    "count_off": "{n} vypnuté",
    "count_unavailable": "{n} nedostupné",
    "mode_heat": "kúrenie",
    "mode_cool": "chladenie",
    "mode_off": "vypnuté",
    "source_override": "ručný režim",
    "source_last": "posledný známy režim, zdroje nie sú dostupné",
    "source_default": "žiadny zdroj nie je dostupný",
    "house_mode": "Režim domu: {mode} – rozhodlo: {by} ({reason})",
    "label_heat": "Krivka kúrenia",
    "label_cool": "Krivka chladenia",
    "label_circulation": "Cirkulácia TUV",
    "param_room": "teplota v izbe",
    "param_design_outdoor": "návrhová vonkajšia teplota",
    "param_design_supply": "návrhová teplota vody",
    "param_exponent": "exponent",
    "param_slope": "strmosť",
    "param_minimum": "minimálna voda",
    "param_maximum": "maximálna voda",
    "param_correction": "korekcia",
    "param_threshold": "prah",
    "param_delta": "delta",
    "circ_cold": "Zapnuté – cirkulácia {t} je pod {on_below}",
    "circ_warming": "Beží – cirkulácia {t}, vypne pri {off_at}",
    "circ_reached": "Vypnuté – cirkulácia {t} dosiahla {off_at}",
    "circ_waiting": "Stojí – cirkulácia {t}, zapne pod {on_below}",
    "circ_disabled": "Vypnuté – cirkulácia je vypnutá prepínačom",
    "circ_no_sensor": "Vypnuté – teplota cirkulácie nie je dostupná",
    "circ_dry_run": " (bez ovládania čerpadla)",
    "kind_heat": "kúrenárske termostaty",
    "kind_cool": "chladiace termostaty",
    "kind_all": "termostaty",
    "switch": "Prepnutie na {mode}: vypínam {off}, potom zapnem {on}",
    "switch_off": "Prepnutie na {mode}: vypínam {off}",
    "nothing": "Prepnutie na {mode}: termostaty sú už v správnom stave",
    "count": "{n} ({names})",
    "turn_on": "Všetky {kind} sú vypnuté – zapínam {on}",
    "stray": "{names} – zapnutý v režime {mode}, vypínam",
    "failed": "Nepodarilo sa vypnúť {names} po {n} pokusoch – zóna môže stále bežať",
    "unavailable": "Nedostupné, nedá sa overiť vypnutie: {names}",
    "zones_dry_run": " (bez ovládania termostatov)",
    "out_dry_run": " (skúšobný režim, nič sa neprepína)",
    "pump_running": "Čerpadlo beží – požiadavka",
    "pump_waiting": "Čerpadlo čaká na otvorenie ventilov – ešte {left} s",
    "pump_run_on": "Čerpadlo dobieha – ešte {left} s",
    "pump_idle": "Čerpadlo vypnuté – bez požiadavky",
    "pump_exercise": "Čerpadlo sa protáča – ešte {left} s",
    "block_pause": "Čakanie medzi kúrením a chladením – ešte {minutes} min",
    "block_dew_point": "Chladenie zastavené – voda {supply} je pod rosným bodom {dew} + 2 K",
    "block_no_humidity": "Chladenie zablokované – chýbajú údaje o vlhkosti",
    "mixer": "Zmiešavač {name}: {reason}",
    "mixer_proposal": "Zmiešavač {name} by: {reason}",
    "mixer_homing": "Zmiešavač {name}: homing, zatváram celú dráhu",
    "mixer_homed": "Zmiešavač {name}: homing hotový, poloha 0 %",
    "mixer_homing_cut": "Zmiešavač {name}: homing prerušený (relé vypol niekto iný), zopakujem",
    "mixer_stopped": "Zmiešavač {name}: núdzové zastavenie, relé bežalo príliš dlho",
    "mixer_both": "Zmiešavač {name}: obe relé zapnuté, vypínam",
    "mixer_stray": "Zmiešavač {name}: relé zapnuté bez príkazu, vypínam",
    "relay_failed": "{label}: príkaz nepotvrdený po {n} pokusoch",
}
_EN = {
    "heating": "Heating",
    "cooling": "Cooling",
    "no_heat": "Not heating",
    "no_cool": "Not cooling",
    "circuit_off": "Off",
    "house_off": "the house mode is off",
    "no_zones": "the circuit has no zones for this mode and runs with the house mode",
    "zones_of": "{n} of {total} zones",
    "nobody": "no zone asks for {what}",
    "what_heat": "heat",
    "what_cool": "cooling",
    "verb_heat": "heating",
    "verb_cool": "cooling",
    "zone_calling": "{verb} {current} → {target}",
    "zone_satisfied": "target reached {current} / {target}",
    "zone_waiting": "within the thermostat's tolerance {current} / {target}",
    "zone_off": "thermostat off",
    "zone_unavailable": "unavailable",
    "count_satisfied": "{n} reached target",
    "count_waiting": "{n} within tolerance",
    "count_off": "{n} off",
    "count_unavailable": "{n} unavailable",
    "mode_heat": "heating",
    "mode_cool": "cooling",
    "mode_off": "off",
    "source_override": "manual override",
    "source_last": "last known mode, no source available",
    "source_default": "no source available",
    "house_mode": "House mode: {mode} – decided by: {by} ({reason})",
    "label_heat": "Heating curve",
    "label_cool": "Cooling curve",
    "label_circulation": "Hot water circulation",
    "param_room": "room temperature",
    "param_design_outdoor": "design outdoor temperature",
    "param_design_supply": "design water temperature",
    "param_exponent": "exponent",
    "param_slope": "slope",
    "param_minimum": "minimum water",
    "param_maximum": "maximum water",
    "param_correction": "correction",
    "param_threshold": "threshold",
    "param_delta": "delta",
    "circ_cold": "On – circulation {t} is below {on_below}",
    "circ_warming": "Running – circulation {t}, stops at {off_at}",
    "circ_reached": "Off – circulation {t} reached {off_at}",
    "circ_waiting": "Stopped – circulation {t}, starts below {on_below}",
    "circ_disabled": "Off – circulation is switched off",
    "circ_no_sensor": "Off – circulation temperature unavailable",
    "circ_dry_run": " (dry run, pump not switched)",
    "kind_heat": "heating thermostats",
    "kind_cool": "cooling thermostats",
    "kind_all": "thermostats",
    "switch": "Switching to {mode}: turning off {off}, then turning on {on}",
    "switch_off": "Switching to {mode}: turning off {off}",
    "nothing": "Switching to {mode}: thermostats are already right",
    "count": "{n} ({names})",
    "turn_on": "All {kind} are off – turning on {on}",
    "stray": "{names} – on in {mode} mode, turning off",
    "failed": "Could not turn off {names} after {n} attempts – the zone may still run",
    "unavailable": "Unavailable, cannot confirm off: {names}",
    "zones_dry_run": " (dry run, thermostats not switched)",
    "out_dry_run": " (dry run, nothing switched)",
    "pump_running": "Pump on – demand",
    "pump_waiting": "Pump waiting for the valves to open – {left} s left",
    "pump_run_on": "Pump running on – {left} s left",
    "pump_idle": "Pump off – no demand",
    "pump_exercise": "Pump exercise – {left} s left",
    "block_pause": "Waiting between heating and cooling – {minutes} min left",
    "block_dew_point": "Cooling stopped – water {supply} is below the dew point {dew} + 2 K",
    "block_no_humidity": "Cooling blocked – no humidity data",
    "mixer": "Mixer {name}: {reason}",
    "mixer_proposal": "Mixer {name} would: {reason}",
    "mixer_homing": "Mixer {name}: homing, closing the full travel",
    "mixer_homed": "Mixer {name}: homing finished, position 0 %",
    "mixer_homing_cut": "Mixer {name}: homing cut short by another switch-off, will retry",
    "mixer_stopped": "Mixer {name}: emergency stop, the relay ran too long",
    "mixer_both": "Mixer {name}: both relays on, turning them off",
    "mixer_stray": "Mixer {name}: relay on without a command, turning it off",
    "relay_failed": "{label}: command not confirmed after {n} attempts",
}
_COUNTED = (ZoneStatus.SATISFIED, ZoneStatus.WAITING, ZoneStatus.OFF, ZoneStatus.UNAVAILABLE)


def _t(language: str) -> dict[str, str]:
    return _SK if language.startswith("sk") else _EN


def _temp(value: float | None) -> str:
    return "?" if value is None else f"{value:.1f} °C"


def zone_text(explained: ZoneExplanation, mode: Mode, language: str) -> str:
    t, zone = _t(language), explained.zone
    return t[f"zone_{explained.status}"].format(
        verb=t["verb_cool" if mode is Mode.COOL else "verb_heat"],
        current=_temp(zone.current),
        target=_temp(zone.target),
    )


def circuit_reason(e: CircuitExplanation, language: str, house_reason: str | None = None) -> str:
    t, cool = _t(language), e.mode is Mode.COOL
    if e.state is CircuitState.OFF:
        return f"{t['circuit_off']} – {t['house_off']}" + (
            f" ({house_reason})" if house_reason else ""
        )
    if e.state in (CircuitState.HEATING, CircuitState.COOLING):
        head = t["cooling" if cool else "heating"]
        if not e.has_zones:
            return f"{head} – {t['no_zones']}"
        count = t["zones_of"].format(n=len(e.calling), total=len(e.zones))
        return f"{head} – {count}: {', '.join(z.zone.name for z in e.calling)}"
    nobody = t["nobody"].format(what=t["what_cool" if cool else "what_heat"])
    counts = [t[f"count_{s}"].format(n=n) for s in _COUNTED if (n := e.count(s))]
    return f"{t['no_cool' if cool else 'no_heat']} – {nobody}" + (
        ": " + ", ".join(counts) if counts else ""
    )


def mode_message(
    mode: Mode, source: ModeSource, decided_by: str | None, reason: str, language: str
) -> str:
    t = _t(language)
    by = t.get(f"source_{source}") or decided_by or "?"
    return t["house_mode"].format(mode=t[f"mode_{mode}"], by=by, reason=reason)


def change_message(label: str, old: float, new: float) -> str:
    return f"{label}: {old:g} → {new:g}"


def curve_parameter_label(kind: str, key: str, language: str) -> str:
    """kind: heat, cool or circulation; e.g. "Heating curve – slope"."""
    t = _t(language)
    return f"{t[f'label_{kind}']} – {t[f'param_{key}']}"


def circulation_message(decision: CirculationDecision, language: str, dry_run: bool) -> str:
    t = _t(language)
    message = t[f"circ_{decision.reason}"].format(
        t=_temp(decision.temperature),
        on_below=_temp(decision.on_below),
        off_at=_temp(decision.off_at),
    )
    return message + (t["circ_dry_run"] if dry_run else "")


def other_zones_kind(mode: Mode, language: str) -> str:
    """Thermostats that must be off in this mode."""
    return _t(language)[{Mode.HEAT: "kind_cool", Mode.COOL: "kind_heat"}.get(mode, "kind_all")]


def zones_message(key: str, mode: Mode, language: str, dry_run: bool = False, **names: Any) -> str:
    """List values become "3 (Kitchen, Office, Hall)"."""
    t = _t(language)
    values = {
        k: t["count"].format(n=len(v), names=", ".join(v)) if isinstance(v, list | tuple) else v
        for k, v in names.items()
    }
    message = t[key].format(mode=t[f"mode_{mode}"], kind=other_zones_kind(mode, language), **values)
    return message + (t["zones_dry_run"] if dry_run else "")


def out_message(key: str, language: str, dry_run: bool = False, **values: Any) -> str:
    """A sentence about a pump or mixer; values are formatted into the text."""
    t = _t(language)
    return t[key].format(**values) + (t["out_dry_run"] if dry_run else "")


def block_text(blocked: Blocked, language: str) -> str:
    return _t(language)[f"block_{blocked.block}"].format(
        minutes=math.ceil(blocked.remaining / 60),
        supply=_temp(blocked.supply),
        dew=_temp(blocked.dew_point),
    )


def pump_text(
    decision: PumpDecision, blocked: Blocked | None, language: str, dry_run: bool = False
) -> str:
    if decision.reason is PumpReason.IDLE and blocked:
        return block_text(blocked, language) + (_t(language)["out_dry_run"] if dry_run else "")
    return out_message(f"pump_{decision.reason}", language, dry_run, left=round(decision.remaining))
