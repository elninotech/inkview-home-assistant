/**
 * InkView — Home Assistant sidebar panel.
 *
 * Vanilla custom element (no build step). HA sets `.hass`, `.narrow`,
 * `.panel`, `.route` on the element; we re-render on every `.hass`
 * assignment. The single number comes from `sensor.inkview_total_energy`
 * (created by the integration's sensor.py); its `contributing_sensors`
 * attribute carries the per-sensor breakdown.
 */

const TOTAL_ENTITY = "sensor.inkview_total_energy";

const fmt = (n, digits = 1) =>
  typeof n === "number" && Number.isFinite(n)
    ? n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })
    : "—";

// HTML-escape anything that originates outside this file (entity attributes,
// friendly names, etc.) before it's interpolated into innerHTML.
const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

class InkViewPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._rendered = false;
  }

  set hass(hass) {
    const first = this._hass === null;
    this._hass = hass;
    if (first) this._renderShell();
    this._updateValues();
    this._fetchCredentials();
  }
  get hass() { return this._hass; }

  set narrow(v) { this._narrow = !!v; this._applyNarrow(); }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  _total() {
    return this._hass?.states[TOTAL_ENTITY] || null;
  }

  _connected() {
    return this._hass?.states["binary_sensor.inkview_connected"];
  }

  _refresh() {
    this._hass?.callService("inkview", "refresh", {});
  }

  _applyNarrow() {
    if (!this._rendered) return;
    this.shadowRoot.host.classList.toggle("narrow", !!this._narrow);
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="page">
        <header class="hero">
          <div class="hero-left">
            <div class="brand">
              <svg class="brand-logo" viewBox="0 0 240 64" role="img" aria-label="InkView" width="120" height="32">
                <rect width="64" height="64" rx="14" fill="#0a0a0a"/>
                <rect x="16" y="14" width="32" height="36" rx="4" fill="#ffffff"/>
                <rect x="22" y="22" width="20" height="3" rx="1.5" fill="#0a0a0a"/>
                <rect x="22" y="30" width="14" height="3" rx="1.5" fill="#0a0a0a" fill-opacity="0.6"/>
                <rect x="22" y="38" width="17" height="3" rx="1.5" fill="#0a0a0a" fill-opacity="0.4"/>
                <text x="80" y="44" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, monospace" font-size="34" font-weight="600" letter-spacing="-0.5" fill="currentColor">InkView</text>
              </svg>
            </div>
            <h1 class="hero-title">Total energy</h1>
            <p class="hero-sub">
              Live kWh sum of the energy sensors you selected for InkView.
            </p>
          </div>
          <div class="hero-right">
            <button class="refresh" id="refresh" title="Refresh now">
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path fill="currentColor" d="M17.65 6.35A8 8 0 1 0 19.73 14h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35Z"/>
              </svg>
              <span>Refresh</span>
            </button>
          </div>
        </header>

        <div class="banner" id="banner" hidden></div>

        <section class="total-card">
          <div class="total-label">Total energy</div>
          <div class="total-value">
            <span class="total-number" id="total-number">—</span>
            <span class="total-unit">kWh</span>
          </div>
          <div class="total-foot" id="total-foot">No data yet</div>
        </section>

        <section class="card">
          <div class="card-head">
            <h2>Contributing sensors</h2>
            <span class="card-sub" id="contrib-count"></span>
          </div>
          <div class="sources" id="sources"></div>
        </section>

        <section class="card" id="connect-card" hidden>
          <div class="card-head">
            <h2>Connect to InkView</h2>
            <span class="card-sub">Paste these into the InkView server</span>
          </div>
          <div class="creds" id="creds"></div>
        </section>

        <footer class="foot">
          <span id="conn-dot" class="conn-dot"></span>
          <span id="conn-label">InkView</span>
          <span class="sep">·</span>
          <span class="readonly" title="InkView tokens are read-only and valid for 1 year">Read-only · 1-year token</span>
          <span class="sep">·</span>
          <a href="/config/integrations/integration/inkview">Integration settings</a>
        </footer>
      </div>
    `;
    this._rendered = true;
    this._applyNarrow();
    this.shadowRoot
      .getElementById("refresh")
      .addEventListener("click", () => this._refresh());
  }

  _updateValues() {
    if (!this._rendered) return;

    const st = this._total();
    const banner = this.shadowRoot.getElementById("banner");
    const number = this.shadowRoot.getElementById("total-number");
    const foot = this.shadowRoot.getElementById("total-foot");

    const value = st ? Number.parseFloat(st.state) : NaN;
    const count = Number(st?.attributes?.sensor_count ?? 0);
    const computedAt = st?.attributes?.computed_at;

    number.textContent = Number.isFinite(value) ? fmt(value, 2) : "—";

    if (!st) {
      banner.hidden = false;
      banner.className = "banner banner-warn";
      banner.textContent =
        "Waiting for the first reading… the total appears a few seconds after setup.";
    } else if (count === 0) {
      banner.hidden = false;
      banner.className = "banner banner-info";
      banner.innerHTML =
        "<strong>No energy sensors selected.</strong> Pick at least one Wh/kWh sensor in " +
        '<a href="/config/integrations/integration/inkview">InkView options</a> to populate the total.';
    } else {
      banner.hidden = true;
    }

    foot.textContent = computedAt
      ? `Updated ${this._relTime(computedAt)} · ${count} sensor${count === 1 ? "" : "s"}`
      : (count ? `${count} sensor${count === 1 ? "" : "s"}` : "No data yet");

    this._renderSources(st);
    this._renderConnection();
  }

  _relTime(iso) {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return "just now";
    const secs = Math.max(0, Math.round((this._now() - t) / 1000));
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.round(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    return `${hrs}h ago`;
  }

  _now() {
    // HA assigns a fresh `hass` object frequently; its last_updated isn't
    // handy here, so fall back to the wall clock for a coarse "x ago".
    return Date.now();
  }

  _renderSources(st) {
    const host = this.shadowRoot.getElementById("sources");
    const countEl = this.shadowRoot.getElementById("contrib-count");
    const rows = Array.isArray(st?.attributes?.contributing_sensors)
      ? st.attributes.contributing_sensors
      : [];

    countEl.textContent = rows.length ? `${rows.length} total` : "";

    if (!rows.length) {
      host.innerHTML = `<div class="empty">Nothing summed yet.</div>`;
      return;
    }

    const max = Math.max(0.0001, ...rows.map((r) => Math.abs(Number(r.kwh) || 0)));
    host.innerHTML = rows
      .map((r) => {
        const kwh = Number(r.kwh) || 0;
        const pct = (Math.abs(kwh) / max) * 100;
        return `
          <div class="src">
            <div class="src-row">
              <span class="src-label">${esc(r.name || r.entity_id)}</span>
              <span class="src-val">${fmt(kwh, 2)} kWh</span>
            </div>
            <div class="src-bar"><div class="src-fill" style="width:${pct}%"></div></div>
          </div>
        `;
      })
      .join("");
  }

  _renderConnection() {
    const conn = this._connected();
    const dot = this.shadowRoot.getElementById("conn-dot");
    const label = this.shadowRoot.getElementById("conn-label");
    if (!conn) {
      dot.className = "conn-dot conn-unknown";
      label.textContent = "InkView";
      return;
    }
    const on = conn.state === "on";
    dot.className = "conn-dot " + (on ? "conn-on" : "conn-off");
    label.textContent = on ? "InkView connected" : "InkView disconnected";
  }

  // --- "Connect to InkView" credentials card -------------------------------

  _fetchCredentials() {
    // Credentials are admin-only (the backend command is require_admin). Skip
    // the call entirely for non-admins so the card stays hidden rather than
    // flashing an "unauthorized" error; the rest of the panel is for everyone.
    if (!this._hass?.user?.is_admin) return;
    // Once per element lifetime; the secret doesn't change between renders
    // and `hass` is reassigned constantly.
    if (this._credsFetched || !this._hass?.connection) return;
    this._credsFetched = true;
    this._hass.connection
      .sendMessagePromise({ type: "inkview/credentials" })
      .then((res) => {
        this._creds = Array.isArray(res?.sessions) ? res.sessions : [];
        this._credsError = null;
        this._renderCredentials();
      })
      .catch((err) => {
        // Let a retry happen on the next hass assignment.
        this._credsFetched = false;
        this._credsError = err?.message || err?.code || "unavailable";
        this._renderCredentials();
      });
  }

  _renderCredentials() {
    const card = this.shadowRoot.getElementById("connect-card");
    const host = this.shadowRoot.getElementById("creds");
    if (!card || !host) return;

    if (this._credsError) {
      card.hidden = false;
      host.innerHTML = `<div class="empty">Couldn't load credentials: ${esc(this._credsError)}</div>`;
      return;
    }
    const sessions = this._creds || [];
    if (!sessions.length) {
      card.hidden = true;
      return;
    }
    card.hidden = false;

    // Fixed-width mask so the secret's length isn't leaked before reveal.
    const MASK = "•".repeat(24);
    host.innerHTML = sessions
      .map((s, i) => {
        const secret = esc(s.secret || "");
        const instance = esc(s.instance_id || "");
        const title = esc(s.title || "InkView");
        return `
          <div class="cred-block">
            ${sessions.length > 1 ? `<div class="cred-title">${title}</div>` : ""}
            <div class="cred-field">
              <label>Instance ID</label>
              <div class="cred-row">
                <code class="cred-value">${instance}</code>
                <button class="mini-btn" data-copy="${instance}">Copy</button>
              </div>
            </div>
            <div class="cred-field">
              <label>Shared secret</label>
              <div class="cred-row">
                <code class="cred-value cred-secret" id="secret-${i}" data-full="${secret}" data-masked="1">${MASK}</code>
                <button class="mini-btn reveal-btn" data-target="secret-${i}">Reveal</button>
                <button class="mini-btn" data-copy="${secret}">Copy</button>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    this._wireCredButtons(host);
  }

  _wireCredButtons(host) {
    const MASK = "•".repeat(24);
    host.querySelectorAll(".reveal-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = this.shadowRoot.getElementById(btn.dataset.target);
        if (!code) return;
        const masked = code.dataset.masked === "1";
        code.textContent = masked ? code.dataset.full : MASK;
        code.dataset.masked = masked ? "0" : "1";
        btn.textContent = masked ? "Hide" : "Reveal";
      });
    });
    host.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const prev = btn.textContent;
        const ok = await this._copyText(btn.dataset.copy);
        btn.textContent = ok ? "Copied" : "Copy failed";
        if (ok) btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = prev;
          btn.classList.remove("copied");
        }, 1200);
      });
    });
  }

  async _copyText(text) {
    // Preferred path — only available in secure contexts (HTTPS / localhost).
    if (window.isSecureContext && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_e) {
        // fall through to the legacy path
      }
    }
    // Fallback for plain-http:// LAN access, where navigator.clipboard is
    // unavailable. A hidden textarea + execCommand still works there.
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
}

const STYLES = `
  :host {
    display: block;
    height: 100%;
    background:
      radial-gradient(1200px 600px at 0% -10%, rgba(255, 199, 89, 0.18), transparent 60%),
      radial-gradient(1000px 600px at 100% 0%, rgba(82, 156, 255, 0.18), transparent 60%),
      var(--primary-background-color, #0f1115);
    color: var(--primary-text-color, #e9ecf1);
    font-family: var(--paper-font-body1_-_font-family, "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
    overflow: auto;
  }
  .page {
    max-width: 900px;
    margin: 0 auto;
    padding: 28px 32px 48px;
    box-sizing: border-box;
  }
  :host(.narrow) .page { padding: 18px 14px 32px; }

  .hero {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    padding: 8px 0 24px;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .brand-logo {
    display: block;
    height: 32px;
    width: auto;
    color: var(--primary-text-color, #e9ecf1);
  }
  .hero-title {
    margin: 6px 0 2px;
    font-size: 30px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  .hero-sub {
    margin: 0;
    color: var(--secondary-text-color, #aab2c0);
    font-size: 14px;
    max-width: 60ch;
  }
  :host(.narrow) .hero-title { font-size: 22px; }

  .refresh {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: var(--primary-text-color, #e9ecf1);
    border-radius: 999px;
    padding: 8px 14px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s ease, transform 0.15s ease;
  }
  .refresh:hover { background: rgba(255, 255, 255, 0.10); }
  .refresh:active { transform: scale(0.98); }

  .banner {
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 18px;
    font-size: 13.5px;
    line-height: 1.5;
  }
  .banner a { color: inherit; text-decoration: underline; }
  .banner-info {
    background: rgba(82, 156, 255, 0.12);
    border: 1px solid rgba(82, 156, 255, 0.30);
    color: #cfe1ff;
  }
  .banner-warn {
    background: rgba(255, 199, 89, 0.12);
    border: 1px solid rgba(255, 199, 89, 0.30);
    color: #ffe3a8;
  }

  .total-card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 24px 26px;
    margin-bottom: 18px;
    position: relative;
    overflow: hidden;
  }
  .total-card::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 4px;
    background: linear-gradient(180deg, #ffc759, #ff7a59);
  }
  .total-label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--secondary-text-color, #aab2c0);
    margin-bottom: 10px;
  }
  .total-value { display: flex; align-items: baseline; gap: 8px; }
  .total-number { font-size: 48px; font-weight: 700; letter-spacing: -0.02em; }
  .total-unit { font-size: 18px; color: var(--secondary-text-color, #aab2c0); }
  .total-foot { margin-top: 10px; font-size: 12px; color: var(--secondary-text-color, #aab2c0); }

  .card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 18px;
  }
  .card-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .card-head h2 { margin: 0; font-size: 15px; font-weight: 600; }
  .card-sub { color: var(--secondary-text-color, #aab2c0); font-size: 12px; }

  .sources { display: grid; gap: 12px; }
  .empty { color: var(--secondary-text-color, #aab2c0); font-size: 13.5px; }
  .src-row { display: flex; justify-content: space-between; align-items: baseline; font-size: 13.5px; margin-bottom: 6px; gap: 12px; }
  .src-label { color: var(--secondary-text-color, #aab2c0); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .src-val { font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
  .src-bar { height: 6px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden; }
  .src-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #ffc759, #ff7a59); transition: width 0.4s ease; }

  .creds { display: grid; gap: 16px; }
  .cred-block { display: grid; gap: 12px; }
  .cred-title { font-size: 13px; font-weight: 600; color: var(--primary-text-color, #e9ecf1); }
  .cred-field { display: grid; gap: 6px; }
  .cred-field label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--secondary-text-color, #aab2c0);
  }
  .cred-row { display: flex; align-items: center; gap: 8px; }
  .cred-value {
    flex: 1;
    min-width: 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
    font-size: 13px;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 8px 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cred-secret { letter-spacing: 0.04em; }
  .mini-btn {
    flex: 0 0 auto;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: var(--primary-text-color, #e9ecf1);
    border-radius: 8px;
    padding: 7px 11px;
    font-size: 12px;
    cursor: pointer;
    transition: background 0.15s ease;
  }
  .mini-btn:hover { background: rgba(255, 255, 255, 0.10); }
  .mini-btn.copied { background: rgba(93, 211, 158, 0.18); border-color: rgba(93, 211, 158, 0.4); }

  .foot {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 14px;
    color: var(--secondary-text-color, #aab2c0);
    font-size: 12px;
  }
  .foot a { color: inherit; }
  .readonly { opacity: 0.9; }
  .conn-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #888;
    box-shadow: 0 0 0 3px rgba(136, 136, 136, 0.18);
  }
  .conn-on { background: #5dd39e; box-shadow: 0 0 0 3px rgba(93, 211, 158, 0.18); }
  .conn-off { background: #ff7a59; box-shadow: 0 0 0 3px rgba(255, 122, 89, 0.18); }
  .conn-unknown { background: #888; }
  .sep { opacity: 0.5; }
`;

if (!customElements.get("inkview-panel")) {
  customElements.define("inkview-panel", InkViewPanel);
}
