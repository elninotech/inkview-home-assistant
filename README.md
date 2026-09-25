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
- **Energy total.** `sensor.inkview_total_energy` adds up your energy
  sensors in kWh.
- **Connection status.** `binary_sensor.inkview_connected` shows whether
  InkView has been in touch recently.
- **Sidebar panel.** Optional InkView view in the Home Assistant sidebar.
- **Security controls.** Services to rotate the shared secret
  (`inkview.rotate_secret`) or revoke every issued token
  (`inkview.revoke_all_tokens`).

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

## Requirements

- Home Assistant 2024.6 or newer. You need 2026.3 or newer to see the
  integration's icon and logo.

## Support

Report bugs and request features on the
[issue tracker](https://github.com/elninotech/inkview-home-assistant/issues).

## License

See [LICENSE](LICENSE).
