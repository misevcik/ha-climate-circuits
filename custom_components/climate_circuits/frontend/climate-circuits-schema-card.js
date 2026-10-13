// Climate Circuits schema card: the heat source and every circuit as a live hydraulic diagram.
// type: custom:climate-circuits-schema-card   (entity: sensor.climate_circuits_mode, optional)
// The integration publishes which entity shows what in the mode sensor's "layout" attribute.

const W = 760;
const ROW = 150;
const TOP = 16;
const TANK = { x: 16, w: 112 };
const HEADER_X = 160;
const MIXER_X = 300;
const SUPPLY_X = 400;
const PUMP_X = 515;
const RAD = { x: 590, w: 150 };
const HOT = "#e8590c";
const COLD = "#1c7ed6";
const OFF = "#adb5bd";

const TEXTS = {
  sk: {
    title: "Schéma kúrenia", heat: "Kúrenie", cool: "Chladenie", off: "Vypnuté",
    dry_run: "Skúšobný režim – nič sa nespína", target: "cieľ", set: "nastavené",
    pump_on: "beží", pump_off: "stojí", no_zone: "žiadna zóna",
    opening: "otvára", closing: "zatvára", homing: "homing", unknown: "poloha neznáma",
    unavailable: "relé nedostupné", starved: "zdroj nestačí", circuit_off: "okruh neovládaný",
    no_source: "bez zdroja", missing: "Nenašla sa integrácia Climate Circuits.",
    mixer: "Zmiešavač", pump: "Čerpadlo",
    hot_water: "Zásobník TÚV", circulation: "Cirkulácia TÚV", circ_return: "spiatočka cirkulácie",
    starts_below: "zapne pod", stops_at: "vypne pri", running: "beží", stopped: "stojí",
    disabled: "vypnutá",
  },
  en: {
    title: "Heating schema", heat: "Heating", cool: "Cooling", off: "Off",
    dry_run: "Dry run – nothing is switched", target: "target", set: "set",
    pump_on: "running", pump_off: "stopped", no_zone: "no zone",
    opening: "opening", closing: "closing", homing: "homing", unknown: "position unknown",
    unavailable: "relay unavailable", starved: "source not enough", circuit_off: "circuit not controlled",
    no_source: "no source", missing: "Climate Circuits integration not found.",
    mixer: "Mixer", pump: "Pump",
    hot_water: "Hot water tank", circulation: "Hot water circulation", circ_return: "circulation return",
    starts_below: "starts below", stops_at: "stops at", running: "running", stopped: "stopped",
    disabled: "disabled",
  },
};

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const num = (v) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? null : Number(v));
let LANG = "en";
const fmt = (v) => Number(v).toLocaleString(LANG, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const deg = (v) => (num(v) === null ? "–" : `${fmt(v)} °C`);

class ClimateCircuitsSchemaCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => {
        const target = ev.composedPath().find((el) => el.dataset && el.dataset.entity);
        if (!target) return;
        this.dispatchEvent(new CustomEvent("hass-more-info", {
          bubbles: true, composed: true, detail: { entityId: target.dataset.entity },
        }));
      });
    }
  }

  set hass(hass) {
    this._hass = hass;
    try {
      const key = this._key();
      if (key !== this._lastKey) {
        this._lastKey = key;
        this._render();
      }
    } catch (err) {
      // Say what went wrong instead of leaving an empty card.
      this._lastKey = null;
      this.shadowRoot.innerHTML = `<ha-card><div class="missing">Climate Circuits: ${esc(err && err.message)}</div></ha-card>`;
    }
  }

  getCardSize() {
    const layout = this._layout();
    return 1 + (layout ? (layout.circuits.length + (layout.hot_water ? 1 : 0)) * 3 : 1);
  }

  static getStubConfig() { return {}; }

  _t(key) {
    const lang = (this._hass && this._hass.language) || "en";
    return (lang.startsWith("sk") ? TEXTS.sk : TEXTS.en)[key];
  }

  _modeEntity() {
    if (!this._hass) return null;
    if (this._config.entity) return this._config.entity;
    return Object.keys(this._hass.states).find((id) => {
      const a = this._hass.states[id].attributes;
      return a && a.layout && Array.isArray(a.layout.circuits);
    }) || null;
  }

  _layout() {
    const id = this._modeEntity();
    const state = id && this._hass.states[id];
    return state && state.attributes.layout ? state.attributes.layout : null;
  }

  _st(id) { return id && this._hass.states[id] ? this._hass.states[id] : null; }
  _val(id) { const s = this._st(id); return s ? s.state : null; }
  _attr(id, a) { const s = this._st(id); return s ? s.attributes[a] : undefined; }

  // Re-render only when something shown changed.
  _key() {
    const layout = this._layout();
    if (!layout) return "none";
    const ids = [layout.mode, layout.control];
    if (!Array.isArray(layout.circuits) || !Array.isArray(layout.sources)) return "none";
    const hw = layout.hot_water;
    if (hw) ids.push(hw.state, hw.temperature, hw.threshold, hw.delta, hw.enabled, hw.tank, hw.tank_setpoint);
    for (const s of layout.sources) ids.push(s.temperature, s.setpoint);
    for (const c of layout.circuits) {
      ids.push(c.state, c.target, c.zones, c.demand, c.pump, c.mixer, c.mixer_state, c.supply, c.control);
    }
    return ids.map((id) => { const s = this._st(id); return s ? s.last_updated : "-"; }).join("|")
      + (this._hass.language || "");
  }

  _render() {
    LANG = (this._hass && this._hass.language) || "en";
    const layout = this._layout();
    if (!layout) {
      this.shadowRoot.innerHTML = `<ha-card><div class="missing">${this._t("missing")}</div></ha-card>`;
      return;
    }
    const mode = this._val(layout.mode);
    const live = this._val(layout.control) === "on";
    const rows = this._rows(layout);
    const height = TOP + (rows.length + (layout.hot_water ? 1 : 0)) * ROW + 8;
    let svg = "";
    for (const group of this._groups(layout, rows)) svg += this._tank(group, mode);
    rows.forEach((row) => { svg += this._circuit(row, mode, live); });
    if (layout.hot_water) svg += this._hotWater(layout.hot_water, TOP + rows.length * ROW);

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head">
          <span class="title">${esc(this._config.title || this._t("title"))}</span>
          <span class="mode ${esc(mode)}" data-entity="${esc(layout.mode)}">${esc(this._t(mode) || mode || "–")}</span>
        </div>
        ${live ? "" : `<div class="dry" data-entity="${esc(layout.control)}">${this._t("dry_run")}</div>`}
        <svg viewBox="0 0 ${W} ${height}" width="100%" role="img">${DEFS}${svg}</svg>
      </ha-card>`;
  }

  // Circuits in the order of their heat source, so each tank spans its own circuits.
  _rows(layout) {
    const order = layout.sources.map((s) => s.id);
    const sorted = [...layout.circuits].sort((a, b) => {
      const ia = order.indexOf(a.source); const ib = order.indexOf(b.source);
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
    });
    return sorted.map((c, i) => ({ c, y: TOP + i * ROW }));
  }

  _groups(layout, rows) {
    const groups = [];
    for (const row of rows) {
      const last = groups[groups.length - 1];
      if (last && last.id === row.c.source) last.rows.push(row);
      else groups.push({ id: row.c.source, source: layout.sources.find((s) => s.id === row.c.source), rows: [row] });
    }
    return groups;
  }

  _tank(group, mode) {
    const top = group.rows[0].y + 14;
    const bottom = group.rows[group.rows.length - 1].y + ROW - 22;
    const first = group.rows[0].y + 50;
    const last = group.rows[group.rows.length - 1].y + 50;
    const cx = TANK.x + TANK.w / 2;
    const hot = mode === "cool" ? COLD : HOT;
    let out = `<line x1="${TANK.x + TANK.w}" y1="${first}" x2="${HEADER_X}" y2="${first}" class="pipe" stroke="${hot}"/>`;
    out += `<line x1="${HEADER_X}" y1="${first}" x2="${HEADER_X}" y2="${last}" class="pipe" stroke="${hot}"/>`;
    if (!group.source) {
      out += `<text x="${cx}" y="${first + 4}" text-anchor="middle" class="muted">${this._t("no_source")}</text>`;
      return out;
    }
    const s = group.source;
    const temperature = this._val(s.temperature);
    const setpoint = s.setpoint ? this._val(s.setpoint) : null;
    out += `<g data-entity="${esc(s.temperature)}" class="click">
      <rect x="${TANK.x}" y="${top}" width="${TANK.w}" height="${bottom - top}" rx="20" fill="url(#cc-tank)" class="outline"/>
      ${this._lines(s.name, 14).map((line, i) => `<text x="${cx}" y="${top + 22 + i * 14}" text-anchor="middle" class="small strong ontank">${esc(line)}</text>`).join("")}
      <text x="${cx}" y="${top + 66}" text-anchor="middle" class="big ontank">${deg(temperature)}</text>
    </g>`;
    if (setpoint !== null) {
      out += `<text x="${cx}" y="${top + 84}" text-anchor="middle" class="tiny click ontank" data-entity="${esc(s.setpoint)}">${this._t("set")} ${deg(setpoint)}</text>`;
    }
    return out;
  }

  _circuit(row, mode, live) {
    const { c, y } = row;
    const pipeY = y + 50;
    const retY = y + ROW - 30;
    const heating = mode !== "cool";
    const hot = heating ? HOT : COLD;
    const pumpOn = this._val(c.pump) === "on";
    const flow = pumpOn ? " flow" : "";
    const supply = num(this._attr(c.mixer, "supply_temperature")) ?? num(this._val(c.supply));
    const target = num(this._val(c.target));
    const diff = supply !== null && target !== null ? supply - target : null;
    const color = diff === null ? OFF : Math.abs(diff) <= 0.5 ? "#2f9e44" : Math.abs(diff) <= 2 ? "#f08c00" : "#e03131";
    let out = "";

    // Pipes: header -> mixer -> radiators, and the return.
    out += `<line x1="${HEADER_X}" y1="${pipeY}" x2="${MIXER_X - 24}" y2="${pipeY}" class="pipe${flow}" stroke="${hot}"/>`;
    out += `<line x1="${MIXER_X + 24}" y1="${pipeY}" x2="${RAD.x}" y2="${pipeY}" class="pipe${flow}" stroke="${pumpOn ? hot : OFF}"/>`;
    const radMid = RAD.x + RAD.w / 2;
    out += `<polyline points="${radMid},${y + 100} ${radMid},${retY} ${TANK.x + TANK.w},${retY}" fill="none" class="pipe thin${flow}" stroke="${pumpOn ? COLD : OFF}"/>`;

    // Mixer.
    if (c.mixer) {
      const position = num(this._val(c.mixer));
      const movement = this._attr(c.mixer, "movement") || "idle";
      const state = this._val(c.mixer_state) || movement;
      out += `<line x1="${MIXER_X}" y1="${retY}" x2="${MIXER_X}" y2="${pipeY + 18}" class="pipe thin${flow}" stroke="${pumpOn ? COLD : OFF}"/>`;
      out += `<g class="click" data-entity="${esc(c.mixer)}">
        <rect x="${MIXER_X - 34}" y="${y + 8}" width="68" height="74" fill="transparent"/>
        <polygon points="${MIXER_X - 24},${pipeY - 13} ${MIXER_X},${pipeY} ${MIXER_X - 24},${pipeY + 13}" class="valve"/>
        <polygon points="${MIXER_X + 24},${pipeY - 13} ${MIXER_X},${pipeY} ${MIXER_X + 24},${pipeY + 13}" class="valve"/>
        <polygon points="${MIXER_X - 12},${pipeY + 26} ${MIXER_X},${pipeY} ${MIXER_X + 12},${pipeY + 26}" class="valve"/>
        <text x="${MIXER_X}" y="${y + 24}" text-anchor="middle" class="big">${position === null ? "?" : Math.round(position)} %${movement === "opening" ? " ▲" : movement === "closing" || movement === "homing" ? " ▼" : ""}</text>
        <rect x="${MIXER_X - 30}" y="${y + 29}" width="60" height="4" rx="2" class="track"/>
        <rect x="${MIXER_X - 30}" y="${y + 29}" width="${0.6 * Math.max(0, Math.min(100, position ?? 0))}" height="4" rx="2" fill="${hot}"/>
      </g>`;
      const label = state !== "idle" ? this._t(state) || state : this._t("mixer");
      out += `<text x="${MIXER_X}" y="${pipeY + 42}" text-anchor="middle" class="small${state === "unavailable" ? " alert" : " muted"}">${esc(label)}</text>`;
    } else {
      out += `<line x1="${MIXER_X - 24}" y1="${pipeY}" x2="${MIXER_X + 24}" y2="${pipeY}" class="pipe" stroke="${hot}"/>`;
    }

    // Supply temperature against the target.
    out += `<g class="click" data-entity="${esc(c.target)}">
      <circle cx="${SUPPLY_X}" cy="${pipeY}" r="9" fill="var(--card-background-color, #fff)" stroke="${color}" stroke-width="3"/>
      <text x="${SUPPLY_X}" y="${y + 24}" text-anchor="middle" class="big" style="fill:${color}">${deg(supply)}</text>
      <text x="${SUPPLY_X}" y="${pipeY + 30}" text-anchor="middle" class="small muted">${this._t("target")} ${deg(target)}</text>
    </g>`;

    // Pump.
    if (c.pump) {
      out += `<g class="click" data-entity="${esc(c.pump)}">
        <circle cx="${PUMP_X}" cy="${pipeY}" r="15" class="${pumpOn ? "pump on" : "pump"}"/>
        <polygon points="${PUMP_X - 6},${pipeY - 8} ${PUMP_X + 9},${pipeY} ${PUMP_X - 6},${pipeY + 8}" fill="${pumpOn ? "#fff" : OFF}"/>
        <text x="${PUMP_X}" y="${pipeY + 32}" text-anchor="middle" class="small muted">${this._t("pump")}: ${this._t(pumpOn ? "pump_on" : "pump_off")}</text>
      </g>`;
    }

    // Radiators with the zones calling for heat.
    const count = num(this._attr(c.zones, "count")) || 0;
    const zones = this._val(c.zones);
    out += `<g class="click" data-entity="${esc(c.state || c.zones)}">
      <rect x="${RAD.x}" y="${y + 14}" width="${RAD.w}" height="86" rx="6" class="radiator${count ? " calling" : ""}" ${count ? `stroke="${hot}"` : ""}/>
      <text x="${radMid}" y="${y + 38}" text-anchor="middle" class="big">${esc(c.name)}</text>
      <text x="${radMid}" y="${y + 58}" text-anchor="middle" class="small">${count ? this._zones(count) : this._t("no_zone")}</text>
      <text x="${radMid}" y="${y + 76}" text-anchor="middle" class="tiny muted">${esc(count ? this._short(zones, 26) : "")}</text>
    </g>`;

    // Warnings under the row.
    const warnings = [];
    if (this._attr(c.mixer, "source_not_enough")) warnings.push(this._t("starved"));
    if (live && c.control && this._val(c.control) !== "on") warnings.push(this._t("circuit_off"));
    if (warnings.length) {
      out += `<text x="${SUPPLY_X}" y="${retY - 10}" text-anchor="middle" class="small alert">⚠ ${esc(warnings.join(" · "))}</text>`;
    }
    return out;
  }

  _zones(n) {
    const lang = (this._hass && this._hass.language) || "en";
    if (lang.startsWith("sk")) return `${n} ${n === 1 ? "zóna" : n < 5 ? "zóny" : "zón"}`;
    return `${n} ${n === 1 ? "zone" : "zones"}`;
  }

  // The hot water tank with its circulation: the pump keeps the return between the limits.
  _hotWater(hw, y) {
    const pipeY = y + 50;
    const retY = y + ROW - 30;
    const top = y + 14;
    const bottom = y + ROW - 22;
    const cx = TANK.x + TANK.w / 2;
    const radMid = RAD.x + RAD.w / 2;
    const state = this._val(hw.state);
    const on = state === "running";
    const flow = on ? " flow" : "";
    const temperature = num(this._val(hw.temperature));
    const threshold = num(this._val(hw.threshold));
    const delta = num(this._val(hw.delta));
    const startsBelow = threshold !== null && delta !== null ? threshold - delta : null;
    const color = temperature === null || startsBelow === null ? OFF
      : temperature >= startsBelow ? "#2f9e44" : "#f08c00";
    const tank = num(this._val(hw.tank));
    const setpoint = num(this._val(hw.tank_setpoint));
    let out = `<g class="click" data-entity="${esc(hw.tank || hw.state)}">
      <rect x="${TANK.x}" y="${top}" width="${TANK.w}" height="${bottom - top}" rx="20" fill="url(#cc-dhw)" class="outline"/>
      ${this._lines(this._t("hot_water"), 14).map((line, i) => `<text x="${cx}" y="${top + 22 + i * 14}" text-anchor="middle" class="small strong ontank">${esc(line)}</text>`).join("")}
      <text x="${cx}" y="${top + 66}" text-anchor="middle" class="big ontank">${deg(tank)}</text>
    </g>`;
    if (setpoint !== null) {
      out += `<text x="${cx}" y="${top + 84}" text-anchor="middle" class="tiny click ontank" data-entity="${esc(hw.tank_setpoint)}">${this._t("set")} ${deg(setpoint)}</text>`;
    }
    out += `<line x1="${TANK.x + TANK.w}" y1="${pipeY}" x2="${RAD.x}" y2="${pipeY}" class="pipe${flow}" stroke="${on ? HOT : OFF}"/>`;
    out += `<polyline points="${radMid},${y + 100} ${radMid},${retY} ${TANK.x + TANK.w},${retY}" fill="none" class="pipe thin${flow}" stroke="${on ? COLD : OFF}"/>`;
    out += `<g class="click" data-entity="${esc(hw.temperature)}">
      <circle cx="${SUPPLY_X}" cy="${pipeY}" r="9" fill="var(--card-background-color, #fff)" stroke="${color}" stroke-width="3"/>
      <text x="${SUPPLY_X}" y="${y + 24}" text-anchor="middle" class="big" style="fill:${color}">${deg(temperature)}</text>
      <text x="${SUPPLY_X}" y="${pipeY + 30}" text-anchor="middle" class="small muted">${this._t("circ_return")}</text>
    </g>`;
    if (threshold !== null) {
      out += `<text x="${SUPPLY_X}" y="${pipeY + 46}" text-anchor="middle" class="small click" data-entity="${esc(hw.threshold)}">${this._t("starts_below")} ${deg(startsBelow)} · ${this._t("stops_at")} ${deg(threshold)}</text>`;
    }
    out += `<g class="click" data-entity="${esc(hw.state)}">
      <circle cx="${PUMP_X}" cy="${pipeY}" r="15" class="${on ? "pump on" : "pump"}"/>
      <polygon points="${PUMP_X - 6},${pipeY - 8} ${PUMP_X + 9},${pipeY} ${PUMP_X - 6},${pipeY + 8}" fill="${on ? "#fff" : OFF}"/>
      <text x="${PUMP_X}" y="${pipeY + 32}" text-anchor="middle" class="small muted">${this._t("pump")}: ${esc(state === "unavailable" ? "–" : this._t(state) || state || "–")}</text>
    </g>`;
    out += `<g class="click" data-entity="${esc(hw.enabled || hw.state)}">
      <rect x="${RAD.x}" y="${y + 14}" width="${RAD.w}" height="86" rx="6" class="radiator${on ? " calling" : ""}" ${on ? `stroke="${HOT}"` : ""}/>
      ${this._lines(this._t("circulation"), 16).map((line, i) => `<text x="${radMid}" y="${y + 40 + i * 18}" text-anchor="middle" class="big">${esc(line)}</text>`).join("")}
    </g>`;
    return out;
  }

  // At most two lines of about n characters, split at spaces.
  _lines(text, n) {
    const words = String(text || "").split(" ");
    const lines = [""];
    for (const w of words) {
      const cur = lines[lines.length - 1];
      if (cur && (cur + " " + w).length > n && lines.length < 2) lines.push(w);
      else lines[lines.length - 1] = cur ? `${cur} ${w}` : w;
    }
    return lines.map((l) => this._short(l, n + 2));
  }

  _short(text, n) {
    const s = String(text || "");
    return s.length > n ? `${s.slice(0, n - 1)}…` : s;
  }
}

const DEFS = `<defs>
  <linearGradient id="cc-tank" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffc9a9"/><stop offset="1" stop-color="#a5d8ff"/>
  </linearGradient>
  <linearGradient id="cc-dhw" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffa8a8"/><stop offset="1" stop-color="#ffe3e3"/>
  </linearGradient>
</defs>`;

const STYLE = `
  ha-card { padding: 12px 12px 8px; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .title { font-size: 18px; font-weight: 500; }
  .mode { padding: 2px 10px; border-radius: 12px; font-size: 13px; cursor: pointer;
    background: var(--secondary-background-color); }
  .mode.heat { background: #ffe8cc; color: #a63c06; }
  .mode.cool { background: #d0ebff; color: #1864ab; }
  .dry { margin-top: 6px; padding: 4px 8px; border-radius: 6px; font-size: 13px; cursor: pointer;
    background: #fff3bf; color: #5c3c00; }
  .missing { padding: 16px; }
  svg { display: block; margin-top: 6px; font-family: var(--ha-font-family-body, Roboto, sans-serif); }
  text { fill: var(--primary-text-color); paint-order: stroke; stroke: var(--card-background-color, #fff);
    stroke-width: 4px; stroke-linejoin: round; }
  .big { font-size: 16px; font-weight: 600; }
  .small { font-size: 12px; }
  .tiny { font-size: 10px; }
  .strong { font-weight: 600; }
  .muted { fill: var(--secondary-text-color); }
  text.ontank { fill: #212529; stroke: none; }
  .alert { fill: #e03131; font-weight: 600; }
  .click { cursor: pointer; }
  .outline { stroke: var(--secondary-text-color); stroke-width: 1.5; }
  .pipe { stroke-width: 6; stroke-linecap: round; fill: none; }
  .pipe.thin { stroke-width: 4; }
  .flow { stroke-dasharray: 14 8; animation: cc-flow 1.2s linear infinite; }
  @keyframes cc-flow { to { stroke-dashoffset: -22; } }
  .valve { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color); stroke-width: 2; }
  .track { fill: var(--divider-color, #ddd); }
  .pump { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color); stroke-width: 2; }
  .pump.on { fill: #2f9e44; stroke: #2f9e44; }
  .radiator { fill: var(--secondary-background-color, #f5f5f5); stroke: var(--divider-color, #ccc); stroke-width: 2; }
  .radiator.calling { stroke-width: 3; }
`;

customElements.define("climate-circuits-schema-card", ClimateCircuitsSchemaCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "climate-circuits-schema-card",
  name: "Climate Circuits schema",
  description: "Heat source, mixers, pumps and circuits with live temperatures.",
});
