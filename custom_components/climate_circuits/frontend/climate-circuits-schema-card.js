// Climate Circuits schema card: the heat source and every circuit as a live hydraulic diagram.
// type: custom:climate-circuits-schema-card   (entity: sensor.climate_circuits_mode, optional)
// The integration publishes which entity shows what in the mode sensor's "layout" attribute.

const ROW = 150;
const TOP = 16;
const HEATER_W = 150; // extra room on the left when a heat generator is shown
// x positions; shifted right when the heat generator (heat pump, boiler) is drawn.
const geometry = (dx) => ({
  w: 760 + dx, heaterX: 16, heaterW: 112, tankX: 16 + dx, tankW: 112, header: 160 + dx,
  mixer: 300 + dx, supply: 400 + dx, pump: 515 + dx, radX: 590 + dx, radW: 150,
});
let G = geometry(0);
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
    auto: "Nastavovanie tepelka", auto_off: "vypnuté", auto_on: "zapnuté",
    auto_dry: "skúšobný režim", auto_paused: "pozastavené do {t} (ručná zmena)",
    auto_set: "nastavené", auto_wants: "chce", auto_margin: "rezerva",
    margin_auto: "učí sa", margin_manual: "ručne",
    auto_idle: "nikto nekúri, nemení sa", auto_cool: "nekúri sa, nemení sa",
    hot_water: "Nádrž TÚV", heater: "Zdroj tepla", heater_out: "výstup", heater_in: "spiatočka", circulation: "Cirkulácia TÚV", circ_return: "spiatočka cirkulácie",
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
    auto: "Heat source setting", auto_off: "off", auto_on: "on",
    auto_dry: "dry run", auto_paused: "paused until {t} (changed by hand)",
    auto_set: "set", auto_wants: "wants", auto_margin: "margin",
    margin_auto: "learned", margin_manual: "manual",
    auto_idle: "no circuit heats, left as it is", auto_cool: "not heating, left as it is",
    hot_water: "Hot water tank", heater: "Heat generator", heater_out: "supply", heater_in: "return", circulation: "Circulation", circ_return: "circulation return",
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

  _lang() {
    return this._config.language || (this._hass && this._hass.language) || "en";
  }

  _t(key) {
    const lang = this._lang();
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
    for (const s of layout.sources) {
      ids.push(s.temperature, s.setpoint, s.setpoint_control, s.margin, s.margin_mode);
      if (s.heater) ids.push(s.heater.supply, s.heater.return);
    }
    for (const c of layout.circuits) {
      ids.push(c.state, c.target, c.zones, c.demand, c.pump, c.mixer, c.mixer_state, c.supply, c.control);
    }
    return ids.map((id) => { const s = this._st(id); return s ? s.last_updated : "-"; }).join("|")
      + (this._hass.language || "");
  }

  _render() {
    LANG = this._lang();
    const layout = this._layout();
    if (!layout) {
      this.shadowRoot.innerHTML = `<ha-card><div class="missing">${this._t("missing")}</div></ha-card>`;
      return;
    }
    const mode = this._val(layout.mode);
    const live = this._val(layout.control) === "on";
    G = geometry(layout.sources.some((s) => s.heater) ? HEATER_W : 0);
    const rows = this._rows(layout);
    const height = TOP + (rows.length + (layout.hot_water ? 1 : 0)) * ROW + 8;
    let svg = "";
    for (const group of this._groups(layout, rows)) svg += this._tank(group, mode);
    rows.forEach((row) => { svg += this._circuit(row, mode, live); });
    if (layout.hot_water) svg += this._hotWater(layout.hot_water, TOP + rows.length * ROW);
    const heated = this._groups(layout, rows).find((g) => g.source && g.source.heater);
    if (heated) svg += this._heater(heated, layout.hot_water ? TOP + rows.length * ROW : null);

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head">
          <span class="title">${esc(this._config.title || this._t("title"))}</span>
          <span class="mode ${esc(mode)}" data-entity="${esc(layout.mode)}">${esc(this._t(mode) || mode || "–")}</span>
        </div>
        ${live ? "" : `<div class="dry" data-entity="${esc(layout.control)}">${this._t("dry_run")}</div>`}
        ${layout.sources.map((src) => this._autoLine(src, live)).join("")}
        <svg viewBox="0 0 ${G.w} ${height}" width="100%" role="img">${DEFS}${svg}</svg>
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
    const cx = G.tankX + G.tankW / 2;
    const hot = mode === "cool" ? COLD : HOT;
    let out = `<line x1="${G.tankX + G.tankW}" y1="${first}" x2="${G.header}" y2="${first}" class="pipe" stroke="${hot}"/>`;
    out += `<line x1="${G.header}" y1="${first}" x2="${G.header}" y2="${last}" class="pipe" stroke="${hot}"/>`;
    if (!group.source) {
      out += `<text x="${cx}" y="${first + 4}" text-anchor="middle" class="muted">${this._t("no_source")}</text>`;
      return out;
    }
    const s = group.source;
    const temperature = this._val(s.temperature);
    const setpoint = s.setpoint ? this._val(s.setpoint) : null;
    out += `<g data-entity="${esc(s.temperature)}" class="click">
      <rect x="${G.tankX}" y="${top}" width="${G.tankW}" height="${bottom - top}" rx="20" fill="url(#cc-tank)" class="outline"/>
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
    out += `<line x1="${G.header}" y1="${pipeY}" x2="${G.mixer - 20}" y2="${pipeY}" class="pipe${flow}" stroke="${hot}"/>`;
    out += `<line x1="${G.mixer + 20}" y1="${pipeY}" x2="${G.radX}" y2="${pipeY}" class="pipe${flow}" stroke="${pumpOn ? hot : OFF}"/>`;
    const radMid = G.radX + G.radW / 2;
    out += `<polyline points="${radMid},${y + 100} ${radMid},${retY} ${G.tankX + G.tankW},${retY}" fill="none" class="pipe thin${flow}" stroke="${pumpOn ? COLD : OFF}"/>`;

    // Mixer.
    if (c.mixer) {
      const position = num(this._val(c.mixer));
      const movement = this._attr(c.mixer, "movement") || "idle";
      const state = this._val(c.mixer_state) || movement;
      out += `<line x1="${G.mixer}" y1="${retY}" x2="${G.mixer}" y2="${pipeY + 20}" class="pipe thin${flow}" stroke="${pumpOn ? COLD : OFF}"/>`;
      out += `<g class="click" data-entity="${esc(c.mixer)}">
        <rect x="${G.mixer - 34}" y="${y}" width="68" height="${pipeY - y + 24}" fill="transparent"/>
        <text x="${G.mixer - 20}" y="${y + 20}" text-anchor="end" class="big">${position === null ? "?" : Math.round(position)} %${movement === "opening" ? " ▲" : movement === "closing" || movement === "homing" ? " ▼" : ""}</text>
        ${this._valve(G.mixer, pipeY, position, hot, COLD, movement !== "idle")}
      </g>`;
      const label = state !== "idle" ? this._t(state) || state : this._t("mixer");
      out += `<text x="${G.mixer}" y="${pipeY + 40}" text-anchor="middle" class="small${state === "unavailable" ? " alert" : " muted"}">${esc(label)}</text>`;
    } else {
      out += `<line x1="${G.mixer - 24}" y1="${pipeY}" x2="${G.mixer + 24}" y2="${pipeY}" class="pipe" stroke="${hot}"/>`;
    }

    // Supply temperature against the target.
    out += `<g class="click" data-entity="${esc(c.target)}">
      <circle cx="${G.supply}" cy="${pipeY}" r="9" fill="var(--card-background-color, #fff)" stroke="${color}" stroke-width="3"/>
      <text x="${G.supply}" y="${y + 24}" text-anchor="middle" class="big" style="fill:${color}">${deg(supply)}</text>
      <text x="${G.supply}" y="${pipeY + 30}" text-anchor="middle" class="small muted">${this._t("target")} ${deg(target)}</text>
    </g>`;

    // Pump.
    if (c.pump) {
      out += `<g class="click" data-entity="${esc(c.pump)}">
        ${this._pumpIcon(G.pump, pipeY, pumpOn)}
        <text x="${G.pump}" y="${pipeY + 34}" text-anchor="middle" class="small muted">${this._t("pump")}: ${this._t(pumpOn ? "pump_on" : "pump_off")}</text>
      </g>`;
    }

    // Radiators with the zones calling for heat.
    const count = num(this._attr(c.zones, "count")) || 0;
    const zones = this._val(c.zones);
    out += `<g class="click" data-entity="${esc(c.state || c.zones)}">
      <rect x="${G.radX}" y="${y + 14}" width="${G.radW}" height="86" rx="6" class="radiator${count ? " calling" : ""}" ${count ? `stroke="${hot}"` : ""}/>
      <text x="${radMid}" y="${y + 38}" text-anchor="middle" class="big">${esc(c.name)}</text>
      <text x="${radMid}" y="${y + 58}" text-anchor="middle" class="small">${count ? this._zones(count) : this._t("no_zone")}</text>
      <text x="${radMid}" y="${y + 76}" text-anchor="middle" class="tiny muted">${esc(count ? this._short(zones, 26) : "")}</text>
    </g>`;

    // Warnings under the row.
    const warnings = [];
    if (this._attr(c.mixer, "source_not_enough")) warnings.push(this._t("starved"));
    if (live && c.control && this._val(c.control) !== "on") warnings.push(this._t("circuit_off"));
    if (warnings.length) {
      out += `<text x="${G.supply}" y="${retY - 10}" text-anchor="middle" class="small alert">⚠ ${esc(warnings.join(" · "))}</text>`;
    }
    return out;
  }

  // Three-way mixing valve: body with three ports, actuator on top, a ring showing the opening.
  _valve(x, y, position, hot, cold, moving) {
    const r = 11;
    const len = 2 * Math.PI * r;
    const p = Math.max(0, Math.min(100, position ?? 0)) / 100;
    return `
      <rect x="${x - 3}" y="${y - 34}" width="6" height="14" class="stem"/>
      <rect x="${x - 13}" y="${y - 44}" width="26" height="14" rx="4" class="actuator${moving ? " moving" : ""}"/>
      <path d="M${x - 20},${y - 8} L${x - 20},${y + 8} M${x + 20},${y - 8} L${x + 20},${y + 8} M${x - 8},${y + 20} L${x + 8},${y + 20}" class="flange"/>
      <circle cx="${x}" cy="${y}" r="18" class="body"/>
      <circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="${cold}" stroke-width="5" opacity="0.55"/>
      <circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="${hot}" stroke-width="5"
        stroke-dasharray="${(len * p).toFixed(1)} ${len.toFixed(1)}" transform="rotate(-90 ${x} ${y})"/>`;
  }

  // Circulation pump: casing with an impeller that turns while it runs.
  _pumpIcon(x, y, on) {
    const blade = "M0,0 C3,-7 9,-9 13,-5";
    const blades = [0, 90, 180, 270].map((a) => `<path d="${blade}" transform="rotate(${a})"/>`).join("");
    return `
      <g transform="translate(${x} ${y})">
        <circle r="18" class="${on ? "casing on" : "casing"}"/>
        <g class="${on ? "impeller on" : "impeller"}">${blades}<circle r="3"/>
          ${on ? '<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="1.2s" repeatCount="indefinite"/>' : ""}
        </g>
      </g>`;
  }

  // The heat generator (heat pump, boiler) heating a source, and the hot water tank through
  // its diverting valve when there is one.
  _heater(group, hotWaterY) {
    const h = group.source.heater;
    const top = group.rows[0].y + 14;
    const x = G.heaterX;
    const w = G.heaterW;
    const cx = x + w / 2;
    const boxTop = top + 10;
    const boxBottom = top + 100;
    const supply = num(this._val(h.supply));
    const ret = num(this._val(h.return));
    const running = supply !== null && ret !== null && supply - ret > 1;
    const flow = running ? " flow" : "";
    const supplyY = top + 30;
    const returnY = boxBottom - 14;
    let out = `<line x1="${x + w}" y1="${supplyY}" x2="${G.tankX}" y2="${supplyY}" class="pipe${flow}" stroke="${running ? HOT : OFF}"/>`;
    out += `<line x1="${G.tankX}" y1="${returnY}" x2="${x + w}" y2="${returnY}" class="pipe thin${flow}" stroke="${running ? COLD : OFF}"/>`;
    if (hotWaterY !== null) {
      // Diverting valve on the supply: the heat generator heats either the tank or the hot water.
      const vx = x + w + 18;
      const dhwY = hotWaterY + 50;
      out += `<polyline points="${vx},${supplyY} ${vx},${dhwY} ${G.tankX},${dhwY}" fill="none" class="pipe thin" stroke="${OFF}"/>`;
      out += `<polygon points="${vx - 7},${supplyY - 12} ${vx + 7},${supplyY - 12} ${vx},${supplyY}" class="body"/>`;
      out += `<polygon points="${vx - 7},${supplyY + 12} ${vx + 7},${supplyY + 12} ${vx},${supplyY}" class="body"/>`;
    }
    out += `<g class="click" data-entity="${esc(h.supply || h.return)}">
      <rect x="${x}" y="${boxTop}" width="${w}" height="${boxBottom - boxTop}" rx="10" class="heater${running ? " on" : ""}"/>
      ${this._lines(h.name || this._t("heater"), 14).map((line, i) => `<text x="${cx}" y="${boxTop + 22 + i * 15}" text-anchor="middle" class="small strong">${esc(line)}</text>`).join("")}
    </g>`;
    if (h.supply) {
      out += `<g class="click" data-entity="${esc(h.supply)}">
        <text x="${cx}" y="${boxTop + 62}" text-anchor="middle" class="small"><tspan class="muted">${this._t("heater_out")}</tspan> <tspan class="strong" style="fill:${HOT}">${deg(supply)}</tspan></text>
      </g>`;
    }
    if (h.return) {
      out += `<g class="click" data-entity="${esc(h.return)}">
        <text x="${cx}" y="${boxTop + 80}" text-anchor="middle" class="small"><tspan class="muted">${this._t("heater_in")}</tspan> <tspan class="strong" style="fill:${COLD}">${deg(ret)}</tspan></text>
      </g>`;
    }
    return out;
  }

  // How the heat source is set from the circuits, for debugging: state, set, wanted and why.
  _autoLine(src, live) {
    if (!src.setpoint_control || !this._st(src.setpoint_control)) return "";
    const on = this._val(src.setpoint_control) === "on";
    const a = (k) => this._attr(src.setpoint, k);
    const paused = a("paused_until");
    let state = this._t(on ? "auto_on" : "auto_off");
    if (on && paused) {
      const t = new Date(paused).toLocaleTimeString(LANG, { hour: "2-digit", minute: "2-digit" });
      state = this._t("auto_paused").replace("{t}", t);
    } else if (on && !live) state = this._t("auto_dry");
    const set = num(this._val(src.setpoint));
    const wanted = num(a("wanted"));
    const margin = num(this._val(src.margin) ?? a("margin"));
    const marginMode = this._val(src.margin_mode) || a("margin_mode");
    let detail;
    if (wanted === null) {
      detail = this._t(a("wanted_reason") === "not_heating" ? "auto_cool" : "auto_idle");
    } else {
      detail = `${this._t("auto_wants")} <b>${deg(wanted)}</b> = ${esc(a("warmest_circuit") || "?")} `
        + `${deg(a("warmest_target"))} + `
        + `<span class="link" data-entity="${esc(src.margin)}">${this._t("auto_margin")} ${deg(margin)}</span>`
        + (marginMode ? ` (<span class="link" data-entity="${esc(src.margin_mode)}">${this._t(`margin_${marginMode}`)}</span>)` : "");
    }
    return `<div class="auto ${on ? (paused ? "paused" : "on") : "off"}" data-entity="${esc(src.setpoint_control)}">
      <b>${this._t("auto")}</b> (${esc(src.name)}): ${esc(state)} ·
      <span class="link" data-entity="${esc(src.setpoint)}">${this._t("auto_set")} ${deg(set)}</span> · ${detail}
    </div>`;
  }

  _zones(n) {
    const lang = this._lang();
    if (lang.startsWith("sk")) return `${n} ${n === 1 ? "zóna" : n < 5 ? "zóny" : "zón"}`;
    return `${n} ${n === 1 ? "zone" : "zones"}`;
  }

  // The hot water tank with its circulation: the pump keeps the return between the limits.
  _hotWater(hw, y) {
    const pipeY = y + 50;
    const retY = y + ROW - 30;
    const top = y + 14;
    const bottom = y + ROW - 22;
    const cx = G.tankX + G.tankW / 2;
    const radMid = G.radX + G.radW / 2;
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
      <rect x="${G.tankX}" y="${top}" width="${G.tankW}" height="${bottom - top}" rx="20" fill="url(#cc-dhw)" class="outline"/>
      ${this._lines(hw.name || this._t("hot_water"), 14).map((line, i) => `<text x="${cx}" y="${top + 22 + i * 14}" text-anchor="middle" class="small strong ontank">${esc(line)}</text>`).join("")}
      <text x="${cx}" y="${top + 66}" text-anchor="middle" class="big ontank">${deg(tank)}</text>
    </g>`;
    if (setpoint !== null) {
      out += `<text x="${cx}" y="${top + 84}" text-anchor="middle" class="tiny click ontank" data-entity="${esc(hw.tank_setpoint)}">${this._t("set")} ${deg(setpoint)}</text>`;
    }
    out += `<line x1="${G.tankX + G.tankW}" y1="${pipeY}" x2="${G.radX}" y2="${pipeY}" class="pipe${flow}" stroke="${on ? HOT : OFF}"/>`;
    out += `<polyline points="${radMid},${y + 100} ${radMid},${retY} ${G.tankX + G.tankW},${retY}" fill="none" class="pipe thin${flow}" stroke="${on ? COLD : OFF}"/>`;
    out += `<g class="click" data-entity="${esc(hw.temperature)}">
      <circle cx="${G.supply}" cy="${pipeY}" r="9" fill="var(--card-background-color, #fff)" stroke="${color}" stroke-width="3"/>
      <text x="${G.supply}" y="${y + 24}" text-anchor="middle" class="big" style="fill:${color}">${deg(temperature)}</text>
      <text x="${G.supply}" y="${pipeY + 30}" text-anchor="middle" class="small muted">${this._t("circ_return")}</text>
    </g>`;
    out += `<g class="click" data-entity="${esc(hw.state)}">
      ${this._pumpIcon(G.pump, pipeY, on)}
      <text x="${G.pump}" y="${pipeY + 34}" text-anchor="middle" class="small muted">${this._t("pump")}: ${esc(state === "unavailable" ? "–" : this._t(state) || state || "–")}</text>
    </g>`;
    out += `<g class="click" data-entity="${esc(hw.enabled || hw.state)}">
      <rect x="${G.radX}" y="${y + 14}" width="${G.radW}" height="86" rx="6" class="radiator${on ? " calling" : ""}" ${on ? `stroke="${HOT}"` : ""}/>
      <text x="${radMid}" y="${y + 38}" text-anchor="middle" class="big">${esc(this._short(this._t("circulation"), 18))}</text>
    </g>`;
    if (threshold !== null) {
      out += `<g class="click" data-entity="${esc(hw.threshold)}">
        <text x="${radMid}" y="${y + 60}" text-anchor="middle" class="small">${this._t("starts_below")} ${deg(startsBelow)}</text>
        <text x="${radMid}" y="${y + 78}" text-anchor="middle" class="small">${this._t("stops_at")} ${deg(threshold)}</text>
      </g>`;
    }
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
  .auto { margin-top: 6px; padding: 4px 8px; border-radius: 6px; font-size: 13px; cursor: pointer;
    background: var(--secondary-background-color); line-height: 1.5; }
  .auto.on { border-left: 4px solid #2f9e44; }
  .auto.paused { border-left: 4px solid #f08c00; }
  .auto.off { border-left: 4px solid var(--divider-color, #ccc); }
  .auto .link { text-decoration: underline dotted; }
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
  .body { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color); stroke-width: 2; }
  .flange { stroke: var(--primary-text-color); stroke-width: 3; stroke-linecap: round; }
  .stem { fill: var(--secondary-text-color); }
  .actuator { fill: var(--secondary-background-color, #eee); stroke: var(--primary-text-color); stroke-width: 1.5; }
  .actuator.moving { fill: #ffd43b; }
  .casing { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color); stroke-width: 2; }
  .casing.on { fill: #2f9e44; stroke: #2b8a3e; }
  .impeller path { fill: none; stroke: var(--secondary-text-color); stroke-width: 3; stroke-linecap: round; }
  .impeller circle { fill: var(--secondary-text-color); }
  .impeller.on path { stroke: #fff; }
  .impeller.on circle { fill: #fff; }
  .heater { fill: var(--secondary-background-color, #f5f5f5); stroke: var(--divider-color, #ccc); stroke-width: 2; }
  .heater.on { stroke: #e8590c; stroke-width: 3; }
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
