<p align="center">
  <img src="custom_components/inkview/brand/logo@2x.png" alt="InkView" width="256">
</p>

# InkView for Home Assistant

Connects Home Assistant to your [InkView](https://inkview.io) e-ink display
over a secure, **read-only** API. You don't need a long-lived access token,
and InkView can never control or change anything in your home.

## Features

- **Read-only access you control.** You pick which sensors InkView can see
  (all of them, or a short list), and you can change the list at any time.
- **Energy at a glance.** The InkView sidebar panel shows how much energy
  your home used, produced, imported and exported today, this week, this
  month or this year. It reads the same statistics as Home Assistant's
  Energy dashboard and follows how you've set that dashboard up.
- **Energy total.** `sensor.inkview_total_energy` adds up the energy meters
  InkView can read, in kWh.
- **Connection status.** `binary_sensor.inkview_connected` shows whether
  InkView has been in touch recently.
- **A link that expires.** The link between Home Assistant and InkView lasts
  a year. Two weeks before it runs out, the panel and Settings → Repairs
  remind you to create a new link or extend the current one.
- **Security controls.** Services to rotate the shared secret
  (`inkview.rotate_secret`), revoke every issued token
  (`inkview.revoke_all_tokens`), or extend the link by a year
  (`inkview.extend_link`).

## Installation

### HACS (recommended)

1. In HACS, search for **InkView** and click **Download**.
2. **Restart Home Assistant.**

### Manual

Copy `custom_components/inkview/` into your `config/custom_components/`
folder, then restart Home Assistant.

## Setup

1. Go to **Settings → Devices & services → Add integration → InkView**.
2. Copy the shared secret that's filled in for you into your InkView
   account, or paste in one that InkView gave you.
3. Choose whether InkView can see all sensors or only the ones you pick.

To change the sensor list later, open the integration and click
**Configure**.

For the panel's solar, grid and home-use figures, set up the
[Energy dashboard](https://www.home-assistant.io/docs/energy/) and share its
meters with InkView. Without it, the panel lists the energy meters InkView
can read.

The panel's **Simulate data** switch fills it with sample figures so you can
preview the screen. It only changes what that browser tab shows: your InkView
display, sensors and history keep using real data.

## Requirements

- Home Assistant 2024.6 or newer. You need 2026.3 or newer to see the
  integration's icon and logo.
- HACS shows a placeholder icon for InkView for now: its store doesn't read
  icons that integrations ship themselves yet
  ([hacs/integration#5171](https://github.com/hacs/integration/issues/5171)).
  Home Assistant itself shows the real icon.

## Support

Report bugs and request features on the
[issue tracker](https://github.com/elninotech/inkview-home-assistant/issues).

## License

See [LICENSE](LICENSE).
