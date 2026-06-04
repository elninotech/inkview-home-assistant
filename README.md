# InkView — Home Assistant integration

Bridges Home Assistant and the [InkView](https://inkview.io) e-ink dashboard
**without** the 10-year long-lived access token. Replaces that with a
scoped, read-only REST namespace at `/api/inkview/v1/*`, plus derived
energy-total sensors and a Lovelace dashboard.

## What's in phase 1

**HTTP namespace** (`/api/inkview/v1/*`):
- `POST /auth/token` — client-credentials over HMAC, returns a read-only,
  1-year JWT
- `GET /states` — bearer-auth, lists the renderable sensors the token may
  see (for the plugin-mode sensor picker)
- `GET /states/{entity_id}` — bearer-auth, allowlist-gated, read-only
- `POST /states/batch` — same as above but for many ids in one round-trip
- `GET /energy/totals` — live kWh sum of the chosen energy sensors plus the
  per-sensor breakdown
- `GET /health` — unauthenticated reachability check
- `/static/*` — serves the integration's logo for use in custom cards

**HA-native UX:**
- **Options flow** with a sensor multi-picker (no more comma-separated
  text). Edit the allowed-entities list any time without re-pairing.
- **Reauth flow** — when the stored secret stops working, HA shows the
  standard red banner with a one-step form to replace it.
- **Repair issue** — surfaces "Energy dashboard not configured" in
  Settings → Repairs with a deep-link to the Energy config page.

**Visibility:**
- **`binary_sensor.inkview_connected`** — on/off based on whether InkView
  has talked to the integration in the last 15 min. Attributes:
  `last_token_minted_at`, `last_state_fetch_at`, `last_failed_auth_at`,
  `tokens_issued_24h`, `failed_auth_24h`.
- **Logbook events** for token issuance / secret rotation / token
  revocation — show up under the InkView device.
- **Diagnostics** download includes session stats + key_version (secrets
  redacted).

**Sensor entities:**
- **`sensor.inkview_total_energy`** — a single derived sensor holding the
  live kWh sum of the chosen energy sensors (or all energy sensors, if the
  allowlist is empty). The per-sensor breakdown that fed the total rides
  along as the `contributing_sensors` attribute.

**Operator services:**
- `inkview.refresh` — force the energy coordinator to tick now.
- `inkview.rotate_secret` — atomically generates a new shared secret
  and shows it in a one-shot persistent notification.
- `inkview.revoke_all_tokens` — bumps an internal key_version so every
  outstanding bearer is rejected; new bearers work immediately.

**Lovelace dashboard** — example YAML at
`lovelace_dashboard.example.yaml` (auto-registration arrives in phase 2).

## Install (manual)

1. Copy `custom_components/inkview/` into your HA config's
   `custom_components/` folder.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add Integration → InkView**.
4. Accept the pre-filled hex secret (or generate one with
   `openssl rand -hex 32` and paste it in). Optionally restrict the
   `/states` endpoint to specific entity IDs.

The config entry's `instance_id` and the secret you used together identify
this HA instance to InkView. Both ends need a copy of the secret.

## Testing the HTTP surface

`tools/sign_request.py` builds an HMAC-signed auth request and prints a
bearer JWT.

```bash
# Find the instance_id under Settings → Devices & services → InkView →
# (the URL contains it after /config/integrations/integration/), or grab
# it from the integration's diagnostics.json.

# 1) Get a bearer (writes JSON to stderr, prints the token on stdout)
TOKEN=$(python tools/sign_request.py \
  --base-url https://your-ha-host:8123 \
  --instance-id 0123456789abcdef0123456789abcdef \
  --secret YOUR_64_HEX_CHARS)

# 2) Fetch a sensor state
curl -H "Authorization: Bearer $TOKEN" \
  https://your-ha-host:8123/api/inkview/v1/states/sensor.solar_power

# 3) Fetch the live energy total + per-sensor breakdown
curl -H "Authorization: Bearer $TOKEN" \
  https://your-ha-host:8123/api/inkview/v1/energy/totals
```

**TLS:** the helper script intentionally does not let you skip TLS
verification — add your HA cert (or its CA) to the system trust store, or
set `SSL_CERT_FILE`. Disabling verification turns the bearer into a
free MITM oracle for anyone on the network path.

## Security model

| Concern | How it's handled |
|---|---|
| Token longevity | 1-year, read-only JWT TTL. Caller re-mints via HMAC whenever it likes. |
| Replay | `ts` window ±60 s, per-instance LRU nonce cache (5 min TTL, 10 k slots). |
| Scope | JWT carries an `allowed_entities` list captured at mint time + a `scope=read` claim; every read endpoint enforces both. |
| Read-only | Only GETs (plus the batch POST, which reads) exposed in `/api/inkview/v1/*`. No services, no writes. |
| Secret storage | Stored in the HA ConfigEntry (encrypted at rest by HA's storage helper). Diagnostics redact it. |
| Instance enumeration | Unknown-instance and bad-signature collapse to the same 401. |
| State access | Reads run synchronously off HA's live state machine (`hass.states`) — no recorder, no executor hop, no event-loop blocking. |
| Token revocation | `inkview.revoke_all_tokens` bumps an internal `kv` (key_version) claim; verify() rejects any token with stale `kv`. Secret stays the same so the InkView side can re-auth immediately. |
| Rate-limited attack surface | Failed bearers, replays, and timestamp-skew all collapse to the same 401 body and increment `failed_auth_24h` for monitoring. |

## Energy data

`GET /api/inkview/v1/energy/totals` returns the **live** kWh sum of the
energy sensors this token is allowed to see (empty allowlist == all
renderable sensors), plus the per-sensor breakdown that fed it. Any sensor
reporting Wh / kWh / MWh counts, normalised to kWh.

It's a pure sum of the *current* state-machine values — no recorder
statistics, no Energy-dashboard coupling, and no simulated data. The same
figure backs the in-HA `sensor.inkview_total_energy` entity, recomputed
every 5 minutes by the energy coordinator.

## File layout

```
custom_components/inkview/
  __init__.py            entry/unload + view registration + coordinator wiring
  manifest.json
  config_flow.py         manual secret entry (phase 2: pairing code)
  const.py
  sensor.py              Tier-1 SensorEntity layer
  binary_sensor.py       inkview_connected liveness indicator
  diagnostics.py         redacted state dump
  repairs.py             "no energy sensors" repair issue
  panel.py               sidebar panel registration
  ws_api.py              admin-gated inkview/credentials WS command
  brand/                 icon/logo served locally by HA (2026.3+), 8 PNGs
  auth/
    bearer.py            HS256 JWT + HMAC, stdlib-only
    stats.py             per-session token/auth telemetry
  energy/
    energy_service.py    live kWh sum of the chosen sensors (state machine)
    coordinator.py       energy DataUpdateCoordinator (5-min ticks)
  http_views/
    _common.py           bearer auth helper + effective allowlist
    auth.py              POST /auth/token
    states.py            GET /states/{entity_id}
    states_list.py       GET /states  (sensor-discovery list)
    states_batch.py      POST /states/batch
    energy.py            GET /energy/totals
    health.py            GET /health
  public/
    logo/                SVG served at /api/inkview/v1/static for custom cards
    panel/               sidebar panel bundle
  translations/en.json
  strings.json

lovelace_dashboard.example.yaml   import this until phase-2 auto-registers
tools/sign_request.py             test helper for the HMAC auth flow
hacs.json
```

## Status

Phase 1 — standalone testing against a real HA, with the secret entered
manually on both sides. Phase 2 swaps the manual secret for a
pairing-code exchange with the InkView cloud and auto-registers the
Lovelace dashboard. Phase 3 ships the Lit-based e-ink preview card.
