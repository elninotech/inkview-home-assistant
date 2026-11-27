// InkView sidebar panel: vanilla custom element, no build step.
// "Simulate data" is panel-only and deliberately not persisted, so a forgotten toggle can't outlive the tab.

const PERIODS = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
  { key: "year", label: "This year" },
];

// In display order.
const GROUPS = {
  solar: { label: "Solar produced", short: "Solar", color: "var(--energy-solar-color, #ff9800)" },
  grid_import: { label: "From the grid", short: "From grid", color: "var(--energy-grid-consumption-color, #488fc2)" },
  grid_export: { label: "To the grid", short: "To grid", color: "var(--energy-grid-return-color, #8353d1)" },
  battery_out: { label: "From the battery", short: "From battery", color: "var(--energy-battery-out-color, #4db6ac)" },
  battery_in: { label: "Into the battery", short: "To battery", color: "var(--energy-battery-in-color, #f06292)" },
};

const REFRESH_MS = 5 * 60 * 1000;
const DAY = 86400;
const WARN_SECONDS = 14 * DAY;
const SECRET_MASK = "•".repeat(24);

// Escape anything from outside this file (names, ids, errors) before it goes into innerHTML.
const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const storage = {
  get(area, key) {
    try { return window[area].getItem(key); } catch (_e) { return null; }
  },
  set(area, key, value) {
    try { window[area].setItem(key, value); } catch (_e) { /* private mode */ }
  },
};

function remainingLabel(seconds) {
  if (seconds <= 0) return "expired";
  const days = Math.floor(seconds / DAY);
  if (days >= 335) return "1 year";
  if (days >= 60) return `${Math.round(days / 30.4)} months`;
  if (days >= 14) return `${Math.floor(days / 7)} weeks`;
  if (days >= 2) return `${days} days`;
  if (days === 1) return "1 day";
  const hours = Math.floor(seconds / 3600);
  return hours >= 1 ? `${hours} hour${hours === 1 ? "" : "s"}` : "less than an hour";
}

// Deterministic PRNG so simulated days don't jitter between renders.
function seeded(seed) {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function periodStart(period, now) {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (period === "week") d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  if (period === "month") d.setDate(1);
  if (period === "year") d.setMonth(0, 1);
  return d;
}

// ~6 kWp solar + small battery home, in the same shape `inkview/energy_summary` returns.
function simulateSummary(period, now = new Date()) {
  const start = periodStart(period, now);
  const totals = { solar: 0, grid_import: 0, grid_export: 0, battery_out: 0, battery_in: 0, used: 0 };

  for (let d = new Date(start); d <= now; d.setDate(d.getDate() + 1)) {
    const rand = seeded(d.getFullYear() * 1000 + d.getMonth() * 40 + d.getDate());
    const yearDay = Math.floor((d - new Date(d.getFullYear(), 0, 0)) / 864e5);
    const summer = 0.5 + 0.5 * Math.cos((2 * Math.PI * (yearDay - 172)) / 365);
    let solar = (4 + 24 * summer) * (0.55 + 0.5 * rand());
    let used = (11 + 7 * (1 - summer)) * (0.85 + 0.3 * rand());

    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      const hour = now.getHours() + now.getMinutes() / 60;
      const sun = Math.min(1, Math.max(0, (hour - 6) / 15));
      solar *= (1 - Math.cos(Math.PI * sun)) / 2; // daylight curve, 06:00–21:00
      used *= Math.min(1, 0.05 + hour / 24);
    }

    // Solar → daytime use → 5 kWh battery → export; battery never covers all of the night.
    const direct = Math.min(solar, used * 0.45);
    const surplus = solar - direct;
    const charge = Math.min(surplus, 5);
    const discharge = Math.min(charge * 0.92, (used - direct) * 0.8);
    totals.solar += solar;
    totals.battery_in += charge;
    totals.grid_export += surplus - charge;
    totals.battery_out += discharge;
    totals.grid_import += used - direct - discharge;
    totals.used += used;
  }

  const r = (v) => Math.round(v * 1000) / 1000;
  const source = (id, name, kwh) => ({ id, name, kwh: r(kwh) });
  const group = (key, rows) => ({ key, kwh: r(rows.reduce((a, s) => a + s.kwh, 0)), sources: rows });
  return {
    period,
    start: start.toISOString(),
    end: now.toISOString(),
    hidden: 0,
    source: "energy_dashboard",
    simulated: true,
    groups: [
      group("solar", [
        source("sim.solar_south", "South roof array", totals.solar * 0.62),
        source("sim.solar_west", "West roof array", totals.solar * 0.38),
      ]),
      group("grid_import", [source("sim.grid_in", "Grid meter, import", totals.grid_import)]),
      group("grid_export", [source("sim.grid_out", "Grid meter, export", totals.grid_export)]),
      group("battery_out", [source("sim.bat_out", "Home battery, discharge", totals.battery_out)]),
      group("battery_in", [source("sim.bat_in", "Home battery, charge", totals.battery_in)]),
    ],
    consumption_kwh: r(totals.used),
    devices: [
      source("sim.heat_pump", "Heat pump", totals.used * 0.27),
      source("sim.ev", "EV charger", totals.used * 0.18),
      source("sim.laundry", "Washer and dryer", totals.used * 0.06),
    ],
    meters: [],
  };
}

class InkViewPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._rendered = false;
    this._period = storage.get("localStorage", "inkview.period") || "today";
    if (!PERIODS.some((p) => p.key === this._period)) this._period = "today";
    this._simulate = false;
    this._summary = null;
    this._summaryError = null;
    this._loading = false;
    this._fetchedAt = null;
    this._creds = null;
    this._credsError = null;
    this._dialogOpener = null;
  }

  set hass(hass) {
    const first = this._hass === null;
    this._hass = hass;
    if (first) {
      this._renderShell();
      this._loadSummary();
      this._startTimer();
    }
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
    this.classList.toggle("dark", !!hass?.themes?.darkMode);
    this._fetchCredentials();
    this._renderStatus();
  }
  get hass() { return this._hass; }

  set narrow(v) {
    this._narrow = !!v;
    this.classList.toggle("narrow", this._narrow);
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = this._narrow;
  }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  connectedCallback() {
    if (this._hass) this._startTimer();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  _startTimer() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      this._loadSummary();
      this._fetchCredentials(true);
    }, REFRESH_MS);
  }

  _lang() {
    return this._hass?.locale?.language || this._hass?.language || undefined;
  }

  _kwh(v) {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    const abs = Math.abs(v);
    const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : abs >= 10 ? 1 : 2;
    return v.toLocaleString(this._lang(), { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  async _loadSummary() {
    if (!this._hass?.connection) return;
    this._loading = true;
    this._renderStatus();
    const period = this._period;
    try {
      const res = await this._hass.connection.sendMessagePromise({ type: "inkview/energy_summary", period });
      if (period !== this._period) return; // superseded by a newer request
      this._summary = res;
      this._summaryError = null;
      this._fetchedAt = Date.now();
    } catch (err) {
      if (period !== this._period) return;
      this._summaryError = err?.message || err?.code || "unknown error";
    }
    this._loading = false;
    this._renderEnergy();
    this._renderStatus();
  }

  _data() {
    return this._simulate ? simulateSummary(this._period) : this._summary;
  }

  _fetchCredentials(force = false) {
    // Backend is require_admin; skip for non-admins so the card stays hidden instead of erroring.
    if (!this._hass?.user?.is_admin || !this._hass?.connection) return;
    if (this._credsFetched && !force) return;
    this._credsFetched = true; // failures retry on the refresh timer
    return this._hass.connection
      .sendMessagePromise({ type: "inkview/credentials" })
      .then((res) => {
        this._creds = Array.isArray(res?.sessions) ? res.sessions : [];
        this._credsError = null;
        this._renderCredentials();
        this._renderStatus();
        this._maybeWarnAboutLink();
        return this._creds;
      })
      .catch((err) => {
        this._credsError = err?.message || err?.code || "unavailable";
        this._renderCredentials();
        return null;
      });
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="page">
        <header class="top">
          <ha-menu-button class="menu"></ha-menu-button>
          <svg class="brand" viewBox="0 0 240 64" role="img" aria-label="InkView">
            <rect width="64" height="64" rx="14" fill="currentColor"/>
            <rect x="16" y="14" width="32" height="36" rx="4" style="fill: var(--iv-bg)"/>
            <rect x="22" y="22" width="20" height="3" rx="1.5" fill="currentColor"/>
            <rect x="22" y="30" width="14" height="3" rx="1.5" fill="currentColor" fill-opacity="0.6"/>
            <rect x="22" y="38" width="17" height="3" rx="1.5" fill="currentColor" fill-opacity="0.4"/>
            <text x="80" y="44" font-family="inherit" font-size="34" font-weight="650" letter-spacing="-0.5" fill="currentColor">InkView</text>
          </svg>
          <div class="top-actions">
            <button class="switch" id="simulate" role="switch" aria-checked="false">
              <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
              <span>Simulate data</span>
            </button>
            <button class="icon-btn" id="refresh" title="Refresh now" aria-label="Refresh now">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M17.65 6.35A8 8 0 1 0 19.73 14h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35Z"/></svg>
            </button>
          </div>
        </header>

        <div class="sim-banner" id="sim-banner" hidden>
          <span><strong>Simulated data.</strong> Nothing below comes from your home, and your InkView display isn't affected.</span>
          <button class="text-btn" id="sim-stop">Show real data</button>
        </div>

        <nav class="periods" id="periods" aria-label="Period">
          ${PERIODS.map((p) => `<button data-period="${p.key}" aria-pressed="${p.key === this._period}">${p.label}</button>`).join("")}
        </nav>

        <figure class="device">
          <div class="bezel">
            <div class="paper" id="paper" aria-live="polite"></div>
          </div>
          <figcaption id="caption">What InkView can show on its screen.</figcaption>
        </figure>

        <section class="section" id="breakdown"></section>

        <section class="section" id="connect" hidden>
          <h2>Connect InkView</h2>
          <p class="lede">Paste these into the InkView app to link this Home Assistant.</p>
          <div id="creds"></div>
        </section>

        <footer class="status">
          <span class="conn"><span id="conn-dot" class="dot"></span><span id="conn-label">InkView</span></span>
          <button class="pill" id="link-pill" hidden></button>
          <span class="readonly">Read-only access</span>
          <a href="/config/integrations/integration/inkview">Integration settings</a>
        </footer>
      </div>
      <div class="scrim" id="scrim" hidden>
        <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title" id="dialog"></div>
      </div>
    `;
    this._rendered = true;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) { menu.hass = this._hass; menu.narrow = this._narrow; }

    $("refresh").addEventListener("click", () => {
      this._hass?.callService("inkview", "refresh", {}).catch(() => {});
      this._loadSummary();
    });
    $("simulate").addEventListener("click", (e) => this._confirmSimulate(e.currentTarget));
    $("sim-stop").addEventListener("click", (e) => this._confirmSimulate(e.currentTarget));
    $("periods").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-period]");
      if (!btn || btn.dataset.period === this._period) return;
      this._period = btn.dataset.period;
      storage.set("localStorage", "inkview.period", this._period);
      this._summary = null;
      this._summaryError = null;
      this._renderEnergy();
      this._loadSummary();
    });
    $("link-pill").addEventListener("click", (e) => this._openLinkDialog(false, e.currentTarget));
    $("scrim").addEventListener("click", (e) => { if (e.target.id === "scrim") this._closeDialog(); });
    this.shadowRoot.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("scrim").hidden) this._closeDialog();
    });
    this._renderEnergy();
  }

  _renderEnergy() {
    if (!this._rendered) return;
    const $ = (id) => this.shadowRoot.getElementById(id);
    this.shadowRoot.querySelectorAll("#periods button").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.period === this._period)));
    $("simulate").setAttribute("aria-checked", String(this._simulate));
    $("sim-banner").hidden = !this._simulate;
    $("paper").classList.toggle("simulated", this._simulate);

    const data = this._data();
    $("paper").innerHTML = this._paperHtml(data);
    $("breakdown").innerHTML = this._breakdownHtml(data);
  }

  _periodTitle() {
    const now = new Date();
    const lang = this._lang();
    if (this._period === "today") return now.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" });
    if (this._period === "week") return `Week of ${periodStart("week", now).toLocaleDateString(lang, { day: "numeric", month: "short" })}`;
    if (this._period === "month") return now.toLocaleDateString(lang, { month: "long", year: "numeric" });
    return String(now.getFullYear());
  }

  _paperHtml(data) {
    const date = `<span class="ink-date">${esc(this._periodTitle())}</span>`;
    if (!data) {
      const msg = this._summaryError ? "Couldn't load energy data" : "Reading your meters…";
      return `<div class="ink-head"><span class="ink-label">${msg}</span>${date}</div>`;
    }

    const groups = Object.fromEntries((data.groups || []).map((g) => [g.key, g]));
    const tiles = [];
    let hero = null;

    if (data.source === "energy_dashboard") {
      if (typeof data.consumption_kwh === "number") hero = { label: "Home used", kwh: data.consumption_kwh };
      for (const key of Object.keys(GROUPS)) {
        const g = groups[key];
        if (!g) continue;
        if (!hero) { hero = { label: GROUPS[key].label, kwh: g.kwh }; continue; }
        tiles.push({ label: GROUPS[key].short, kwh: g.kwh });
      }
    } else {
      const meters = [...(data.meters || [])].sort((a, b) => (b.kwh ?? -1) - (a.kwh ?? -1));
      if (meters.length) hero = { label: meters[0].name, kwh: meters[0].kwh };
      meters.slice(1, 5).forEach((m) => tiles.push({ label: m.name, kwh: m.kwh }));
    }

    if (!hero) {
      return `
        <div class="ink-head"><span class="ink-label">Nothing to show yet</span>${date}</div>
        <p class="ink-note">InkView can't read any energy meters. Pick some in the integration options.</p>`;
    }

    const imp = groups.grid_import?.kwh;
    const used = data.consumption_kwh;
    let selfUse = "";
    if (typeof used === "number" && used > 0 && typeof imp === "number") {
      const pct = Math.max(0, Math.min(100, Math.round((1 - imp / used) * 100)));
      selfUse = `
        <div class="ink-self">
          <span>Self-sufficiency</span>
          <span class="dither" role="img" aria-label="${pct} percent"><span style="width:${pct}%"></span></span>
          <span class="ink-pct">${pct}%</span>
        </div>`;
    }

    return `
      <div class="ink-head"><span class="ink-label">${esc(hero.label)}</span>${date}</div>
      <div class="ink-hero"><span class="ink-num">${this._kwh(hero.kwh)}</span><span class="ink-unit">kWh</span></div>
      ${tiles.length ? `<dl class="ink-tiles">${tiles.map((t) => `
        <div><dt>${esc(t.label)}</dt><dd>${typeof t.kwh === "number" ? `${this._kwh(t.kwh)} <small>kWh</small>` : `<small>No data</small>`}</dd></div>`).join("")}
      </dl>` : ""}
      ${selfUse}
      ${data.simulated ? `<span class="stamp" aria-hidden="true">Sample</span>` : ""}`;
  }

  _breakdownHtml(data) {
    if (this._summaryError && !this._simulate) {
      return `
        <h2>Energy</h2>
        <p class="notice error">Couldn't load energy data (${esc(this._summaryError)}). Check that the Recorder integration is running, then refresh.</p>`;
    }
    if (!data) return "";

    const optionsLink = `<a href="/config/integrations/integration/inkview">InkView options</a>`;
    const notes = [];
    if (data.hidden > 0) {
      notes.push(`${data.hidden} meter${data.hidden === 1 ? "" : "s"} from your Energy dashboard ${data.hidden === 1 ? "isn't" : "aren't"} shared with InkView, so home use can't be worked out. Share ${data.hidden === 1 ? "it" : "them"} in ${optionsLink}.`);
    }
    if (data.source === "sensors") {
      notes.push(`Set up the <a href="/config/energy">Energy dashboard</a> to see solar, grid and home use separately.`);
    }

    const row = (s, color, max) => {
      const pct = typeof s.kwh === "number" && max > 0 ? Math.max(2, (Math.abs(s.kwh) / max) * 100) : 0;
      return `
        <li>
          <span class="row-name" title="${esc(s.id)}">${esc(s.name)}</span>
          <span class="row-val">${typeof s.kwh === "number" ? `${this._kwh(s.kwh)} kWh` : `<span class="muted" title="No statistics recorded for this period">No data</span>`}</span>
          <span class="bar"><span style="width:${pct}%;background:${color}"></span></span>
        </li>`;
    };

    const blocks = [];
    const all = [
      ...(data.groups || []).flatMap((g) => g.sources),
      ...(data.devices || []),
      ...(data.meters || []),
    ];
    const max = Math.max(0, ...all.map((s) => Math.abs(s.kwh ?? 0)));

    for (const g of data.groups || []) {
      const meta = GROUPS[g.key];
      if (!meta) continue;
      blocks.push(`
        <div class="group">
          <h3><span class="swatch" style="background:${meta.color}"></span>${meta.label}<span class="group-total">${this._kwh(g.kwh)} kWh</span></h3>
          <ul>${g.sources.map((s) => row(s, meta.color, max)).join("")}</ul>
        </div>`);
    }
    if ((data.devices || []).length) {
      blocks.push(`
        <div class="group">
          <h3><span class="swatch" style="background:var(--iv-muted)"></span>Devices</h3>
          <ul>${data.devices.map((s) => row(s, "var(--iv-muted)", max)).join("")}</ul>
        </div>`);
    }
    if ((data.meters || []).length) {
      blocks.push(`
        <div class="group">
          <ul>${data.meters.map((s) => row(s, "var(--iv-accent)", max)).join("")}</ul>
        </div>`);
    }
    if (!blocks.length && !notes.length) {
      notes.push(`No energy meters are shared with InkView. Pick sensors that measure energy in ${optionsLink}.`);
    }

    return `
      <h2>Where the numbers come from</h2>
      ${notes.map((n) => `<p class="notice">${n}</p>`).join("")}
      ${blocks.join("")}`;
  }

  _linkInfo() {
    const withExpiry = (this._creds || []).filter((s) => typeof s.link_expires_at === "number");
    if (!withExpiry.length) return null;
    const soonest = withExpiry.reduce((a, b) => (a.link_expires_at <= b.link_expires_at ? a : b));
    return { ...soonest, remaining: soonest.link_expires_at - Date.now() / 1000 };
  }

  _renderStatus() {
    if (!this._rendered) return;
    const $ = (id) => this.shadowRoot.getElementById(id);

    const conn = this._hass?.states["binary_sensor.inkview_connected"];
    $("conn-dot").className = "dot " + (!conn ? "" : conn.state === "on" ? "on" : "off");
    $("conn-label").textContent = !conn ? "InkView" : conn.state === "on" ? "InkView connected" : "InkView not connected";

    const link = this._linkInfo();
    const pill = $("link-pill");
    pill.hidden = !link;
    if (link) {
      const left = remainingLabel(link.remaining);
      pill.textContent = link.remaining <= 0 ? "Link expired" : `Link valid for ${left}`;
      pill.className = "pill" + (link.remaining <= 0 ? " bad" : link.remaining <= WARN_SECONDS ? " warn" : "");
      pill.title = `Expires ${new Date(link.link_expires_at * 1000).toLocaleString(this._lang())}. Click to manage.`;
    }

    let caption;
    if (this._simulate) caption = "Sample figures for previewing the screen.";
    else if (this._loading && !this._summary) caption = "Loading…";
    else if (this._fetchedAt) caption = `Energy used and produced ${PERIODS.find((p) => p.key === this._period).label.toLowerCase()}, from Home Assistant's statistics. Updated ${this._ago(this._fetchedAt)}.`;
    else caption = "What InkView can show on its screen.";
    $("caption").textContent = caption;
  }

  _ago(ms) {
    const secs = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (secs < 60) return "just now";
    const mins = Math.round(secs / 60);
    return mins < 60 ? `${mins} min ago` : `${Math.round(mins / 60)} h ago`;
  }

  _renderCredentials() {
    const card = this.shadowRoot.getElementById("connect");
    const host = this.shadowRoot.getElementById("creds");
    if (!card || !host) return;
    if (this._credsError) {
      card.hidden = false;
      host.innerHTML = `<p class="notice">Couldn't load the link details (${esc(this._credsError)}).</p>`;
      return;
    }
    const sessions = this._creds || [];
    card.hidden = !sessions.length;
    host.innerHTML = sessions.map((s, i) => `
      <div class="cred-block">
        ${sessions.length > 1 ? `<h3>${esc(s.title || "InkView")}</h3>` : ""}
        ${this._credFieldsHtml(s, `s${i}`)}
      </div>`).join("");
    this._wireCredButtons(host);
  }

  _credFieldsHtml(s, idPrefix) {
    const instance = esc(s.instance_id || "");
    const secret = esc(s.secret || "");
    return `
      <div class="field">
        <label for="${idPrefix}-id">Instance ID</label>
        <div class="field-row">
          <code class="value" id="${idPrefix}-id">${instance}</code>
          <button class="btn" data-copy="${instance}">Copy</button>
        </div>
      </div>
      <div class="field">
        <label for="${idPrefix}-secret">Shared secret</label>
        <div class="field-row">
          <code class="value" id="${idPrefix}-secret" data-full="${secret}" data-masked="1">${SECRET_MASK}</code>
          <button class="btn reveal" data-target="${idPrefix}-secret" aria-controls="${idPrefix}-secret">Show</button>
          <button class="btn" data-copy="${secret}">Copy</button>
        </div>
      </div>`;
  }

  _wireCredButtons(host) {
    host.querySelectorAll(".reveal").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = this.shadowRoot.getElementById(btn.dataset.target);
        if (!code) return;
        const masked = code.dataset.masked === "1";
        code.textContent = masked ? code.dataset.full : SECRET_MASK;
        code.dataset.masked = masked ? "0" : "1";
        btn.textContent = masked ? "Hide" : "Show";
      });
    });
    host.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ok = await this._copyText(btn.dataset.copy);
        btn.textContent = ok ? "Copied" : "Copy failed";
        btn.classList.toggle("done", ok);
        setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1400);
      });
    });
  }

  async _copyText(text) {
    // navigator.clipboard needs a secure context (HTTPS / localhost).
    if (window.isSecureContext && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_e) {
        // fall through to the legacy path
      }
    }
    // Plain-http LAN access: execCommand still works there.
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (_e) {
      return false;
    }
  }

  // `run` may be async; the dialog closes when it settles unless it resolves to false.
  _openDialog({ title, body, actions }, opener) {
    const scrim = this.shadowRoot.getElementById("scrim");
    const dlg = this.shadowRoot.getElementById("dialog");
    if (opener) this._dialogOpener = opener;
    dlg.innerHTML = `
      <h2 id="dlg-title">${title}</h2>
      <div class="dlg-body">${body}</div>
      <p class="dlg-error" id="dlg-error" hidden></p>
      <div class="dlg-actions">
        ${actions.map((a, i) => `<button class="btn ${a.kind || "quiet"}" data-i="${i}">${a.label}</button>`).join("")}
      </div>`;
    scrim.hidden = false;
    this._wireCredButtons(dlg);
    const buttons = [...dlg.querySelectorAll(".dlg-actions button")];
    buttons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = actions[Number(btn.dataset.i)];
        if (!action.run) { this._closeDialog(); return; }
        buttons.forEach((b) => (b.disabled = true));
        try {
          const keepOpen = (await action.run()) === false;
          if (!keepOpen) this._closeDialog();
        } catch (err) {
          const e = this.shadowRoot.getElementById("dlg-error");
          if (e) {
            e.hidden = false;
            e.textContent = `That didn't work: ${err?.message || err?.code || "unknown error"}. Nothing was changed.`;
          }
        } finally {
          buttons.forEach((b) => (b.disabled = false));
        }
      });
    });
    (dlg.querySelector(".btn.primary") || buttons[0])?.focus();
  }

  _closeDialog() {
    const scrim = this.shadowRoot.getElementById("scrim");
    if (scrim.hidden) return;
    scrim.hidden = true;
    this.shadowRoot.getElementById("dialog").innerHTML = "";
    this._dialogOpener?.focus?.();
    this._dialogOpener = null;
  }

  _confirmSimulate(opener) {
    const turningOn = !this._simulate;
    const apply = () => {
      this._simulate = turningOn;
      this._renderEnergy();
      this._renderStatus();
    };
    this._openDialog(
      turningOn
        ? {
            title: "Show simulated data?",
            body: "<p>This panel switches to generated sample figures so you can preview the screen. Your InkView display, sensors and Home Assistant history keep using real data.</p>",
            actions: [
              { label: "Show simulated data", kind: "primary", run: apply },
              { label: "Cancel", kind: "text" },
            ],
          }
        : {
            title: "Go back to real data?",
            body: "<p>This panel shows your home's real energy figures again.</p>",
            actions: [
              { label: "Show real data", kind: "primary", run: apply },
              { label: "Cancel", kind: "text" },
            ],
          },
      opener,
    );
  }

  _maybeWarnAboutLink() {
    const link = this._linkInfo();
    if (!link || link.remaining > WARN_SECONDS) return;
    // Once per browser session per link, so it doesn't nag on every visit.
    const key = `inkview.linkWarned.${link.entry_id}.${link.link_expires_at}`;
    if (storage.get("sessionStorage", key)) return;
    storage.set("sessionStorage", key, "1");
    if (this.shadowRoot.getElementById("scrim").hidden) this._openLinkDialog(true);
  }

  _openLinkDialog(urgent, opener) {
    const link = this._linkInfo();
    if (!link) return;
    const expired = link.remaining <= 0;
    const until = new Date(link.link_expires_at * 1000).toLocaleDateString(this._lang(), { day: "numeric", month: "long", year: "numeric" });
    const title = expired
      ? "Your InkView link has expired"
      : urgent
        ? `Your InkView link expires in ${remainingLabel(link.remaining)}`
        : "InkView link";
    const status = expired
      ? "InkView can't read your sensors any more, so its screen has stopped updating."
      : `The link works until ${esc(until)}. After that InkView can't read your sensors and its screen stops updating.`;

    this._openDialog(
      {
        title,
        body: `
          <p>${status}</p>
          <p><strong>Create a new link</strong> (recommended): a fresh secret, valid for a year. InkView stops updating until you paste it into the InkView app.</p>
          <p><strong>Extend the current link</strong>: the same secret keeps working for another year. Nothing changes on the InkView side.</p>`,
        actions: [
          { label: "Create new link", kind: "primary", run: () => this._rotateLink() },
          { label: "Extend by 1 year", kind: "quiet", run: () => this._extendLink() },
          { label: urgent ? "Not now" : "Close", kind: "text" },
        ],
      },
      opener,
    );
  }

  async _extendLink() {
    await this._hass.callService("inkview", "extend_link", {});
    await this._reloadCredentials();
  }

  async _rotateLink() {
    await this._hass.callService("inkview", "rotate_secret", {});
    const sessions = await this._reloadCredentials();
    if (!sessions) {
      this._openDialog({
        title: "New link created",
        body: `<p>The old secret no longer works, but the new one couldn't be loaded yet. Reopen the InkView panel to copy it.</p>`,
        actions: [{ label: "Close", kind: "primary" }],
      });
      return false;
    }
    this._openDialog({
      title: "New link created",
      body: `
        <p>Paste these into the InkView app to re-link it. The old secret no longer works.</p>
        ${sessions.map((s, i) => `
          ${sessions.length > 1 ? `<h3>${esc(s.title || "InkView")}</h3>` : ""}
          ${this._credFieldsHtml(s, `new${i}`)}`).join("")}`,
      actions: [{ label: "Done", kind: "primary" }],
    });
    return false; // keep open: it now shows the new credentials
  }

  // The service reloads the config entry, so poll until every session shows the
  // new secret or expiry. Resolves to the sessions, or null if that never happens.
  async _reloadCredentials() {
    const before = new Map((this._creds || []).map((s) => [s.entry_id, s]));
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 300));
      const sessions = await this._fetchCredentials(true);
      const updated = sessions?.length && sessions.every((s) => {
        const old = before.get(s.entry_id);
        return !old || old.secret !== s.secret || old.link_expires_at !== s.link_expires_at;
      });
      if (updated) return sessions;
    }
    return null;
  }
}

const STYLES = `
  :host {
    --iv-bg: var(--primary-background-color, #f4f5f6);
    --iv-surface: var(--card-background-color, #ffffff);
    --iv-text: var(--primary-text-color, #1d2125);
    --iv-muted: var(--secondary-text-color, #5d646c);
    --iv-line: var(--divider-color, rgba(0, 0, 0, 0.12));
    --iv-accent: var(--primary-color, #03a9f4);
    --iv-warn: var(--warning-color, #f0a020);
    --iv-bad: var(--error-color, #db4437);
    --iv-good: var(--success-color, #43a047);

    /* E-ink screen: same in both themes, it's a physical object. */
    --iv-paper: #e2e2dc;
    --iv-ink: #262624;
    --iv-ink-soft: #62625d;
    --iv-bezel: #2f3135;
    --iv-ink-font: Charter, "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif;

    display: block;
    min-height: 100%;
    background: var(--iv-bg);
    color: var(--iv-text);
    font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif));
    -webkit-font-smoothing: antialiased;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  a { color: var(--iv-accent); }
  button { font: inherit; color: inherit; }
  button:focus-visible, a:focus-visible { outline: 2px solid var(--iv-accent); outline-offset: 2px; }

  .page { max-width: 880px; margin: 0 auto; padding: 20px 32px 40px; }
  :host(.narrow) .page { padding: 8px 16px 32px; }

  .top { display: flex; align-items: center; gap: 12px; min-height: 56px; }
  .menu { display: none; margin-left: -8px; }
  :host(.narrow) .menu { display: block; }
  .brand { height: 26px; width: auto; color: var(--iv-text); }
  .top-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }

  .switch {
    display: inline-flex; align-items: center; gap: 10px;
    background: none; border: 0; padding: 8px 10px; border-radius: 8px;
    cursor: pointer; font-size: 14px; color: var(--iv-text);
  }
  .switch:hover { background: color-mix(in srgb, var(--iv-text) 6%, transparent); }
  .switch-track {
    position: relative; width: 34px; height: 20px; border-radius: 10px;
    background: color-mix(in srgb, var(--iv-text) 22%, transparent);
    transition: background 0.15s ease;
  }
  .switch-thumb {
    position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
    background: var(--iv-surface); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    transition: transform 0.15s ease;
  }
  .switch[aria-checked="true"] .switch-track { background: var(--iv-warn); }
  .switch[aria-checked="true"] .switch-thumb { transform: translateX(14px); }
  :host(.narrow) .switch span:last-child { font-size: 13px; }

  .icon-btn {
    display: inline-grid; place-items: center; width: 40px; height: 40px;
    border-radius: 50%; border: 0; background: none; cursor: pointer; color: var(--iv-muted);
  }
  .icon-btn:hover { background: color-mix(in srgb, var(--iv-text) 6%, transparent); color: var(--iv-text); }

  .sim-banner {
    display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    margin: 8px 0 4px; padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.45;
    background: color-mix(in srgb, var(--iv-warn) 16%, var(--iv-surface));
    border: 1px solid color-mix(in srgb, var(--iv-warn) 45%, transparent);
  }
  .text-btn { background: none; border: 0; padding: 4px 2px; cursor: pointer; color: var(--iv-text); font-weight: 600; text-decoration: underline; text-underline-offset: 3px; }

  .periods { display: flex; gap: 4px; margin: 16px 0 14px; overflow-x: auto; scrollbar-width: none; }
  .periods button {
    flex: 0 0 auto; border: 1px solid transparent; background: none; cursor: pointer;
    padding: 7px 14px; border-radius: 999px; font-size: 14px; color: var(--iv-muted);
  }
  .periods button:hover { color: var(--iv-text); }
  .periods button[aria-pressed="true"] {
    color: var(--iv-text); font-weight: 600;
    background: var(--iv-surface); border-color: var(--iv-line);
  }

  .device { margin: 0 0 32px; }
  .bezel {
    background: var(--iv-bezel); border-radius: 22px; padding: 16px;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06) inset, 0 12px 28px -18px rgba(0, 0, 0, 0.55);
  }
  :host(.narrow) .bezel { border-radius: 16px; padding: 10px; }
  .paper {
    position: relative; overflow: hidden;
    min-height: 240px; padding: 26px 30px 24px; border-radius: 4px;
    background: var(--iv-paper); color: var(--iv-ink);
    font-family: var(--iv-ink-font);
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08), inset 0 2px 6px rgba(0, 0, 0, 0.12);
  }
  :host(.narrow) .paper { padding: 18px 18px 16px; min-height: 200px; }
  /* E-ink reflects ambient light; in a dark UI it reads as a dimmer sheet. */
  :host(.dark) .paper { --iv-paper: #c9c9c3; }
  .paper.simulated {
    background:
      repeating-linear-gradient(-45deg, transparent 0 14px, rgba(0, 0, 0, 0.035) 14px 15px),
      var(--iv-paper);
  }
  figcaption { margin-top: 10px; font-size: 13px; color: var(--iv-muted); line-height: 1.45; }

  .ink-head { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  .ink-label { font-size: 19px; }
  .ink-date { font-size: 15px; color: var(--iv-ink-soft); font-style: italic; }
  .ink-hero { display: flex; align-items: baseline; gap: 10px; margin: 6px 0 18px; }
  .ink-num { font-size: clamp(56px, 11vw, 92px); line-height: 1; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: lining-nums tabular-nums; }
  .ink-unit { font-size: 22px; color: var(--iv-ink-soft); }
  .ink-tiles {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); gap: 14px 20px;
    margin: 0; padding-top: 14px; border-top: 2px solid var(--iv-ink);
  }
  .ink-tiles dt { font-size: 14px; color: var(--iv-ink-soft); }
  .ink-tiles dd { margin: 2px 0 0; font-size: 26px; font-weight: 700; font-variant-numeric: lining-nums tabular-nums; }
  .ink-tiles small { font-size: 14px; font-weight: 400; color: var(--iv-ink-soft); }
  .ink-self { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; margin-top: 18px; font-size: 15px; }
  .ink-pct { font-weight: 700; font-variant-numeric: tabular-nums; }
  /* A dithered bar, the way an e-ink panel draws grey. */
  .dither { position: relative; height: 12px; border: 1.5px solid var(--iv-ink); }
  .dither span {
    position: absolute; inset: 0 auto 0 0;
    background: repeating-conic-gradient(var(--iv-ink) 0 25%, transparent 0 50%) 0 0 / 3px 3px;
  }
  .ink-note { font-size: 17px; line-height: 1.5; max-width: 46ch; margin: 14px 0 0; }
  .stamp {
    position: absolute; right: 30px; top: 74px; transform: rotate(-6deg);
    border: 2px solid var(--iv-ink); padding: 2px 10px; border-radius: 4px;
    font-size: 15px; font-weight: 700; letter-spacing: 0.04em; opacity: 0.7;
  }

  .section { margin-bottom: 32px; }
  .section h2, .dialog h2 { margin: 0 0 12px; font-size: 18px; font-weight: 600; letter-spacing: -0.01em; }
  .lede { margin: -6px 0 14px; color: var(--iv-muted); font-size: 14px; }
  .notice {
    margin: 0 0 14px; padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.5;
    background: color-mix(in srgb, var(--iv-accent) 9%, var(--iv-surface));
  }
  .notice.error { background: color-mix(in srgb, var(--iv-bad) 10%, var(--iv-surface)); }
  .group { padding: 14px 0; border-top: 1px solid var(--iv-line); }
  .group:first-of-type { border-top: 0; }
  .group h3 { display: flex; align-items: center; gap: 10px; margin: 0 0 8px; font-size: 15px; font-weight: 600; }
  .swatch { width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto; }
  .group-total { margin-left: auto; font-variant-numeric: tabular-nums; }
  .group ul { list-style: none; margin: 0; padding: 0 0 0 20px; display: grid; gap: 10px; }
  .group li { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; font-size: 14px; }
  .row-name { color: var(--iv-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row-val { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .muted { color: var(--iv-muted); }
  .bar { grid-column: 1 / -1; height: 4px; border-radius: 2px; background: color-mix(in srgb, var(--iv-text) 7%, transparent); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: 2px; }

  .cred-block { display: grid; gap: 14px; }
  .cred-block + .cred-block { margin-top: 20px; }
  .cred-block h3, .dlg-body h3 { margin: 0; font-size: 15px; font-weight: 600; }
  .field { display: grid; gap: 6px; }
  .field label { font-size: 13px; color: var(--iv-muted); }
  .field-row { display: flex; gap: 8px; align-items: center; }
  .value {
    flex: 1; min-width: 0; padding: 9px 12px; border-radius: 8px;
    background: var(--iv-surface); border: 1px solid var(--iv-line);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .btn {
    flex: 0 0 auto; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 14px;
    border: 1px solid var(--iv-line); background: var(--iv-surface); color: var(--iv-text);
  }
  .btn:hover { background: color-mix(in srgb, var(--iv-text) 5%, var(--iv-surface)); }
  .btn:disabled { opacity: 0.6; cursor: progress; }
  .btn.done { border-color: var(--iv-good); color: var(--iv-good); }
  .btn.primary { background: var(--iv-accent); border-color: var(--iv-accent); color: var(--text-primary-color, #fff); font-weight: 600; }
  .btn.primary:hover { background: color-mix(in srgb, var(--iv-accent) 88%, #000); }
  .btn.text { border-color: transparent; background: none; color: var(--iv-muted); }

  .status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 18px; padding-top: 16px; border-top: 1px solid var(--iv-line); font-size: 13px; color: var(--iv-muted); }
  .status a { color: inherit; }
  .conn { display: inline-flex; align-items: center; gap: 8px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--iv-muted); }
  .dot.on { background: var(--iv-good); }
  .dot.off { background: var(--iv-bad); }
  .pill {
    border: 1px solid var(--iv-line); background: var(--iv-surface); cursor: pointer;
    padding: 5px 12px; border-radius: 999px; font-size: 13px; color: var(--iv-text);
  }
  .pill.warn { border-color: var(--iv-warn); background: color-mix(in srgb, var(--iv-warn) 14%, var(--iv-surface)); }
  .pill.bad { border-color: var(--iv-bad); color: var(--iv-bad); }

  .scrim {
    position: fixed; inset: 0; z-index: 10; display: grid; place-items: center; padding: 16px;
    background: rgba(0, 0, 0, 0.45);
  }
  .scrim[hidden] { display: none; }
  .dialog {
    width: min(480px, 100%); max-height: calc(100vh - 32px); overflow: auto;
    padding: 24px; border-radius: 16px;
    background: var(--iv-surface); color: var(--iv-text);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
    animation: rise 0.16s ease-out;
  }
  .dlg-body { display: grid; gap: 12px; font-size: 14.5px; line-height: 1.55; }
  .dlg-body p { margin: 0; }
  .dlg-error { margin: 14px 0 0; color: var(--iv-bad); font-size: 14px; }
  .dlg-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 22px; }
  @keyframes rise { from { opacity: 0; transform: translateY(6px); } }

  @media (prefers-reduced-motion: reduce) {
    .dialog { animation: none; }
    .switch-track, .switch-thumb { transition: none; }
  }
  @media (max-width: 520px) {
    .top { flex-wrap: wrap; }
    .ink-tiles { grid-template-columns: repeat(2, 1fr); }
    .dlg-actions { flex-direction: column-reverse; align-items: stretch; }
  }
`;

if (!customElements.get("inkview-panel")) {
  customElements.define("inkview-panel", InkViewPanel);
}
