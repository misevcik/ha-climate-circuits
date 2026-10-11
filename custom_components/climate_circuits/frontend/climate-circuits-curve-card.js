// Climate Circuits weather curve card: drag the handles, saved with climate_circuits.set_curve.
// type: custom:climate-circuits-curve-card, entity: sensor.<circuit>_target_water_temperature

const RANGES = { heat: [-20, 25], cool: [15, 40] };
const COOL_SLOPE_OFFSET = 10; // the cooling slope handle sits this far above room temp
const COLORS = { heat: "#e8590c", cool: "#1c7ed6" };
const W = 600;
const H = 340;
const M = { left: 48, right: 16, top: 16, bottom: 40 };

const TEXTS = {
  sk: {
    heat: "Kúrenie", cool: "Chladenie", outdoor: "Vonku °C", water: "Voda °C", now: "Teraz",
    room: "Izbová tepl.:", slope: "Strmosť", design_outdoor: "Min. vonkajšia tepl.:",
    design_supply: "Voda pri min. vonk. tepl.:",
    exponent: "Exponent", minimum: "Min", maximum: "Max", correction: "Korekcia",
    hint_heat: "Ťahaj návrhový bod (◆), bod izby (●) a čiary min/max, alebo klikni na hodnotu.",
    hint_cool: "Ťahaj bod strmosti (◆), otočný bod (●) a čiary min/max, alebo klikni na hodnotu.",
    saving: "Ukladám…", missing: "Entita nemá údaje krivky (Climate Circuits).",
  },
  en: {
    heat: "Heating", cool: "Cooling", outdoor: "Outdoor °C", water: "Water °C", now: "Now",
    room: "Room Temp.:", slope: "Slope", design_outdoor: "Min. External Temp.:",
    design_supply: "Water at Min. Ext. Temp.:",
    exponent: "Exponent", minimum: "Min", maximum: "Max", correction: "Correction",
    hint_heat: "Drag the design point (◆), the room point (●) and the min/max lines, or click a value.",
    hint_cool: "Drag the slope handle (◆), the pivot (●) and the min/max lines, or click a value.",
    saving: "Saving…", missing: "The entity has no curve data (Climate Circuits).",
  },
};

const STEPS = { slope: 0.05, exponent: 0.05 }; // others 0.5
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
const roundTo = (v, step) => Math.round(v / step) * step;
const fmt = (v, digits = 1) => Number(v).toFixed(digits);

// Same model as core/curve.py raw_value.
function rawValue(view, c, outdoor) {
  if (view === "heat") {
    const load = Math.max(c.room - outdoor, 0) / Math.max(c.room - c.design_outdoor, 1);
    return c.room + (c.design_supply - c.room) * load ** (1 / Math.max(c.exponent, 0.5)) + c.correction;
  }
  return c.room - c.slope * (outdoor - c.room) + c.correction;
}

const limited = (view, c, outdoor) => clamp(rawValue(view, c, outdoor), c.minimum, c.maximum);

class ClimateCircuitsCurveCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity is required (sensor.<circuit>_target_water_temperature)");
    }
    this._config = config;
    this._view = null;
    this._draft = null;
    this._drag = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const attrs = this._attrs();
    // Drop the draft once Home Assistant reports the saved values.
    if (this._draft && !this._drag && attrs) {
      const saved = attrs[`${this._currentView(attrs)}_curve`];
      const keys = Object.keys(this._draft);
      if (saved && keys.every((k) => Math.abs(saved[k] - this._draft[k]) < 1e-6)) {
        this._draft = null;
        this._saving = false;
      }
    }
    if (!this._drag && !this._editing) this._render();
  }

  getCardSize() { return 6; }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => hass.states[id].attributes && hass.states[id].attributes.heat_curve
    );
    return { entity: entity || "" };
  }

  _t(key) {
    const lang = (this._hass && this._hass.language) || "en";
    return (lang.startsWith("sk") ? TEXTS.sk : TEXTS.en)[key];
  }

  _attrs() {
    const state = this._hass && this._hass.states[this._config.entity];
    return state && state.attributes && state.attributes.heat_curve ? state.attributes : null;
  }

  _currentView(attrs) {
    if (this._view) return this._view;
    return attrs.house_mode === "cool" ? "cool" : "heat";
  }

  _curve(attrs, view) {
    return this._draft ? { ...attrs[`${view}_curve`], ...this._draft } : attrs[`${view}_curve`];
  }

  _handles(view, c) {
    if (view === "heat") {
      return {
        main: { key: "design_supply", x: c.design_outdoor, y: c.design_supply + c.correction },
        pivot: { key: "room", x: c.room, y: c.room + c.correction },
      };
    }
    const x = c.room + COOL_SLOPE_OFFSET;
    return {
      main: { key: "slope", x, y: rawValue(view, c, x) },
      pivot: { key: "correction", x: c.room, y: c.room + c.correction },
    };
  }

  // The fixed range, widened so both handles always stay inside with a margin.
  _scales(view, curve) {
    const h = this._handles(view, curve);
    const xs = [h.main.x, h.pivot.x];
    const x0 = Math.min(RANGES[view][0], Math.floor((Math.min(...xs) - 2.5) / 5) * 5);
    const x1 = Math.max(RANGES[view][1], Math.ceil((Math.max(...xs) + 2.5) / 5) * 5);
    const lo = Math.min(curve.minimum, h.pivot.y, h.main.y);
    const hi = Math.max(curve.maximum, h.pivot.y, h.main.y);
    return { x0, x1, y0: Math.floor(lo / 5) * 5 - 5, y1: Math.ceil(hi / 5) * 5 + 5 };
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const attrs = this._attrs();
    if (!attrs) {
      this.shadowRoot.innerHTML = `<ha-card><div class="msg">${this._t("missing")}</div></ha-card>`;
      return;
    }
    const view = this._currentView(attrs);
    const curve = this._curve(attrs, view);
    // While dragging the Y axis stays still, so the curve does not jump under the pointer;
    // the X axis may grow (the room point moves right as the room temperature rises).
    const fresh = this._scales(view, curve);
    const s = this._drag ? { ...fresh, y0: this._drag.scales.y0, y1: this._drag.scales.y1 } : fresh;
    this._scalesNow = s;
    const color = COLORS[view];
    const px = (x) => M.left + ((x - s.x0) / (s.x1 - s.x0)) * (W - M.left - M.right);
    const py = (y) => M.top + ((s.y1 - y) / (s.y1 - s.y0)) * (H - M.top - M.bottom);
    const inside = (y) => clamp(y, s.y0, s.y1);

    const grid = [];
    for (let y = s.y0; y <= s.y1; y += 5) {
      grid.push(
        `<line x1="${M.left}" y1="${py(y)}" x2="${W - M.right}" y2="${py(y)}" class="grid"/>`,
        `<text x="${M.left - 6}" y="${py(y) + 4}" text-anchor="end" class="axis">${y}</text>`
      );
    }
    for (let x = Math.ceil(s.x0 / 5) * 5; x <= s.x1; x += 5) {
      grid.push(
        `<line x1="${px(x)}" y1="${M.top}" x2="${px(x)}" y2="${H - M.bottom}" class="grid"/>`,
        `<text x="${px(x)}" y="${H - M.bottom + 16}" text-anchor="middle" class="axis">${x}</text>`
      );
    }

    const limitedPoints = [];
    const rawPoints = [];
    for (let x = s.x0; x <= s.x1 + 1e-9; x += 0.5) {
      limitedPoints.push(`${px(x).toFixed(1)},${py(limited(view, curve, x)).toFixed(1)}`);
      rawPoints.push(`${px(x).toFixed(1)},${py(inside(rawValue(view, curve, x))).toFixed(1)}`);
    }

    let now = "";
    const outdoor = attrs.outdoor_temperature;
    if (attrs.house_mode === view && outdoor !== null && outdoor !== undefined) {
      const target = limited(view, curve, outdoor);
      const x = clamp(outdoor, s.x0, s.x1);
      now =
        `<circle cx="${px(x)}" cy="${py(target)}" r="6" fill="${color}" class="now"/>` +
        `<text x="${W - M.right}" y="${M.top + 12}" text-anchor="end" class="nowtext" fill="${color}">` +
        `${this._t("now")}: ${fmt(outdoor)} °C → ${fmt(target)} °C</text>`;
    }

    const line = (key, y) =>
      `<line x1="${M.left}" y1="${py(y)}" x2="${W - M.right}" y2="${py(y)}" class="limit" stroke="${color}"/>` +
      `<line x1="${M.left}" y1="${py(y)}" x2="${W - M.right}" y2="${py(y)}" class="hit ns" data-handle="${key}"/>` +
      `<text x="${M.left + 6}" y="${py(y) - 5}" class="limittext" fill="${color}">${this._t(key)} ${fmt(y)}</text>`;

    const h = this._handles(view, curve);
    const main = { x: px(h.main.x), y: py(inside(h.main.y)) };
    const pivot = { x: px(h.pivot.x), y: py(inside(h.pivot.y)) };

    const values = Object.keys(attrs[`${view}_curve`])
      .map((k) => {
        const step = STEPS[k] || 0.5;
        const value =
          this._editing === k
            ? `<input type="number" step="${step}" value="${curve[k]}" data-edit="${k}">`
            : `<span class="num">${fmt(curve[k], step < 0.5 ? 2 : 1)}</span>`;
        return `<span class="value" data-key="${k}"><b>${this._t(k)}</b> ${value}</span>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 16px 16px; }
        .head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
        .title { font-size: 1.1em; font-weight: 500; }
        .tabs button { border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
          padding: 4px 12px; border-radius: 16px; cursor: pointer; font: inherit; }
        .tabs button.on { background: ${color}; border-color: ${color}; color: #fff; }
        svg { width: 100%; height: auto; touch-action: none; user-select: none; }
        .grid { stroke: var(--divider-color); stroke-width: 1; }
        .axis { fill: var(--secondary-text-color); font-size: 11px; }
        .label { fill: var(--secondary-text-color); font-size: 12px; }
        .limit { stroke-dasharray: 5 4; stroke-width: 1.5; opacity: .7; }
        .limittext { font-size: 11px; }
        .hit { stroke: transparent; stroke-width: 14; }
        .ns { cursor: ns-resize; }
        .handle { stroke: var(--card-background-color, #fff); stroke-width: 2; }
        .now { stroke: var(--primary-text-color); stroke-width: 2; }
        .nowtext { font-size: 13px; font-weight: 600; }
        .values { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .9em; margin-top: 4px; }
        .hint { color: var(--secondary-text-color); font-size: .8em; margin-top: 6px; }
        .hint.error { color: var(--error-color, #db4437); }
        .value { cursor: pointer; }
        .num { border-bottom: 1px dashed var(--secondary-text-color); }
        .value input { width: 5em; font: inherit; color: inherit; background: none;
          border: 1px solid ${color}; border-radius: 4px; padding: 0 4px; }
        .msg { padding: 8px 0; }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${this._config.title || ""}</div>
          <div class="tabs">
            <button data-view="heat" class="${view === "heat" ? "on" : ""}">${this._t("heat")}</button>
            <button data-view="cool" class="${view === "cool" ? "on" : ""}">${this._t("cool")}</button>
          </div>
        </div>
        <svg viewBox="0 0 ${W} ${H}">
          ${grid.join("")}
          <text x="${(M.left + W - M.right) / 2}" y="${H - 6}" text-anchor="middle" class="label">${this._t("outdoor")}</text>
          <text x="12" y="${(M.top + H - M.bottom) / 2}" text-anchor="middle" class="label"
            transform="rotate(-90 12 ${(M.top + H - M.bottom) / 2})">${this._t("water")}</text>
          ${line("maximum", curve.maximum)}
          ${line("minimum", curve.minimum)}
          <polyline points="${rawPoints.join(" ")}" fill="none" stroke="${color}"
            stroke-dasharray="2 4" opacity=".5"/>
          <polyline points="${limitedPoints.join(" ")}" fill="none" stroke="${color}" stroke-width="3"/>
          ${now}
          <rect x="${main.x - 7}" y="${main.y - 7}" width="14" height="14" fill="${color}"
            class="handle" transform="rotate(45 ${main.x} ${main.y})"/>
          <circle cx="${main.x}" cy="${main.y}" r="14" class="hit ns" fill="transparent" data-handle="${h.main.key}"/>
          <circle cx="${pivot.x}" cy="${pivot.y}" r="7" fill="${color}" class="handle"/>
          <circle cx="${pivot.x}" cy="${pivot.y}" r="14" class="hit ns" fill="transparent" data-handle="${h.pivot.key}"/>
        </svg>
        <div class="values">${values}</div>
        <div class="hint ${this._error ? "error" : ""}">${
          this._error || (this._saving ? this._t("saving") : this._t(`hint_${view}`))
        }</div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll(".tabs button").forEach((b) =>
      b.addEventListener("click", () => {
        this._view = b.dataset.view;
        this._draft = null;
        this._editing = null;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll(".value").forEach((el) =>
      el.addEventListener("click", () => {
        if (this._editing === el.dataset.key) return;
        this._editing = el.dataset.key;
        this._error = null;
        this._render();
      })
    );
    const input = this.shadowRoot.querySelector("input[data-edit]");
    if (input) {
      input.focus();
      input.select();
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") input.blur();
        if (ev.key === "Escape") {
          this._editing = null;
          this._render();
        }
      });
      input.addEventListener("blur", () => this._commit(view, input.dataset.edit, input.value));
    }
    const svg = this.shadowRoot.querySelector("svg");
    svg.querySelectorAll("[data-handle]").forEach((el) =>
      el.addEventListener("pointerdown", (ev) => this._start(ev, el.dataset.handle, view))
    );
    svg.addEventListener("pointermove", (ev) => this._move(ev));
    svg.addEventListener("pointerup", (ev) => this._end(ev));
    svg.addEventListener("pointercancel", (ev) => this._end(ev));
  }

  _dataY(ev) {
    const svg = this.shadowRoot.querySelector("svg");
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    const s = this._drag.scales;
    return s.y1 - ((p.y - M.top) / (H - M.top - M.bottom)) * (s.y1 - s.y0);
  }

  _start(ev, handle, view) {
    ev.preventDefault();
    const base = this._curve(this._attrs(), view);
    this._drag = { handle, view, scales: this._scalesNow, base };
    this._draft = { ...(this._draft || {}) };
    this.shadowRoot.querySelector("svg").setPointerCapture(ev.pointerId);
  }

  _move(ev) {
    if (!this._drag) return;
    const { handle } = this._drag;
    const y = this._dataY(ev);
    const c = { ...this._drag.base, ...this._draft };
    const d = this._draft;
    if (handle === "maximum") {
      d.maximum = clamp(roundTo(y, 0.5), c.minimum + 0.5, 90);
    } else if (handle === "minimum") {
      d.minimum = clamp(roundTo(y, 0.5), -30, c.maximum - 0.5);
    } else if (handle === "design_supply") {
      d.design_supply = clamp(roundTo(y - c.correction, 0.5), c.room + 1, 90);
    } else if (handle === "room") {
      // The room point moves along the diagonal: the whole curve shifts.
      d.room = clamp(roundTo(y - c.correction, 0.5), Math.max(5, c.design_outdoor + 1), 35);
    } else if (handle === "correction") {
      d.correction = clamp(roundTo(y - c.room, 0.5), -10, 10);
    } else if (handle === "slope") {
      d.slope = clamp(roundTo((c.room + c.correction - y) / COOL_SLOPE_OFFSET, 0.05), 0, 5);
    }
    this._render();
  }

  _end(ev) {
    if (!this._drag) return;
    const { view, base } = this._drag;
    this._drag = null;
    const saved = this._attrs()[`${view}_curve`];
    const changed = Object.fromEntries(
      Object.entries(this._draft || {}).filter(
        ([k, v]) => Math.abs(v - base[k]) > 1e-9 || Math.abs(v - saved[k]) > 1e-9
      )
    );
    if (!Object.keys(changed).length) {
      this._draft = null;
      this._render();
      return;
    }
    this._save(view, changed);
  }

  _commit(view, key, text) {
    if (this._editing !== key) return; // Escape already cancelled
    this._editing = null;
    const value = parseFloat(text);
    const current = this._curve(this._attrs(), view)[key];
    if (Number.isNaN(value) || Math.abs(value - current) < 1e-9) {
      this._render();
      return;
    }
    this._draft = { ...(this._draft || {}), [key]: value };
    this._save(view, { [key]: value });
  }

  _save(view, changed) {
    this._saving = true;
    this._error = null;
    this._hass
      .callService("climate_circuits", "set_curve", {
        entity_id: this._config.entity,
        mode: view,
        ...changed,
      })
      .then(() => setTimeout(() => this._settle(), 3000))
      .catch((err) => {
        this._error = (err && err.message) || String(err);
        this._settle();
      });
    this._render();
  }

  _settle() {
    this._draft = null;
    this._saving = false;
    this._render();
  }
}

if (!customElements.get("climate-circuits-curve-card")) {
  customElements.define("climate-circuits-curve-card", ClimateCircuitsCurveCard);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: "climate-circuits-curve-card",
  name: "Climate Circuits – weather curve",
  description: "Interactive weather curve of a heating and cooling circuit.",
  preview: false,
});
