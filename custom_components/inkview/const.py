"""Constants for the InkView Home Assistant integration."""

DOMAIN = "inkview"
VERSION = "0.4.1"

URL_PREFIX = "/api/inkview/v1"

# Bearer tokens are long-lived and strictly read-only (scope="read"); they
# only work against InkView's own read endpoints and can never control HA.
DEFAULT_TOKEN_TTL_SECONDS = 365 * 24 * 60 * 60  # 1 year
DEFAULT_TOKEN_LEEWAY_SECONDS = 5
TOKEN_SCOPE = "read"

HMAC_TIMESTAMP_WINDOW_SECONDS = 60
HMAC_NONCE_TTL_SECONDS = 300
HMAC_NONCE_CACHE_SIZE = 10_000
MAX_AUTH_BODY_BYTES = 4096
MAX_BATCH_BODY_BYTES = 16_384
MAX_BATCH_ENTITY_IDS = 64

ENERGY_UPDATE_INTERVAL_MINUTES = 5
# binary_sensor.inkview_connected flips off after this many seconds without
# any successful auth/state activity from the InkView side.
CONNECTED_THRESHOLD_SECONDS = 15 * 60

CONF_SECRET = "secret"
CONF_ALLOWED_ENTITIES = "allowed_entities"
CONF_INSTANCE_ID = "instance_id"
CONF_KEY_VERSION = "key_version"
CONF_SHOW_SIDEBAR_PANEL = "show_sidebar_panel"
# "Expose all sensors" toggle in the config/options flow. When True, the
# allowed-entities allowlist is cleared (empty == all renderable sensors).
CONF_ALL_SENSORS = "all_sensors"

DATA_SESSIONS = "sessions"
DATA_NONCE_CACHES = "nonce_caches"
DATA_VIEWS_REGISTERED = "views_registered"
DATA_COORDINATORS = "coordinators"
DATA_SERVICES_REGISTERED = "services_registered"
DATA_STATIC_REGISTERED = "static_registered"
DATA_PANEL_REGISTERED = "panel_registered"
DATA_WS_REGISTERED = "ws_registered"

PANEL_URL_PATH = "inkview"
PANEL_TITLE = "InkView"
PANEL_ICON = "mdi:lightning-bolt"
PANEL_MODULE_URL = f"{URL_PREFIX}/panel/inkview-panel.js"

SERVICE_REFRESH = "refresh"
SERVICE_ROTATE_SECRET = "rotate_secret"
SERVICE_REVOKE_ALL_TOKENS = "revoke_all_tokens"

# Raised when the total-energy sum has no contributing energy sensors —
# either none were selected, or none of the selected ones report Wh/kWh/MWh.
ISSUE_NO_ENERGY_SENSORS = "no_energy_sensors"
