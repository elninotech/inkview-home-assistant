"""Constants for the InkView Home Assistant integration."""

DOMAIN = "inkview"
VERSION = "1.1.0"

URL_PREFIX = "/api/inkview/v1"

# Bearers are read-only and only work against InkView's own read endpoints.
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
# binary_sensor.inkview_connected goes off after this long without activity.
CONNECTED_THRESHOLD_SECONDS = 15 * 60

CONF_SECRET = "secret"
CONF_ALLOWED_ENTITIES = "allowed_entities"
CONF_INSTANCE_ID = "instance_id"
CONF_KEY_VERSION = "key_version"
CONF_SHOW_SIDEBAR_PANEL = "show_sidebar_panel"
# When False, only the allowlist applies; an empty list means "read nothing".
CONF_ALL_SENSORS = "all_sensors"
# Unix time at which the link (instance_id + shared secret) stops working.
CONF_LINK_EXPIRES_AT = "link_expires_at"

LINK_LIFETIME_SECONDS = 365 * 24 * 60 * 60
LINK_WARN_SECONDS = 14 * 24 * 60 * 60
LINK_CHECK_INTERVAL_MINUTES = 60

DATA_SESSIONS = "sessions"
DATA_NONCE_CACHES = "nonce_caches"
DATA_VIEWS_REGISTERED = "views_registered"
DATA_COORDINATORS = "coordinators"
DATA_SERVICES_REGISTERED = "services_registered"
DATA_PANEL_REGISTERED = "panel_registered"
DATA_WS_REGISTERED = "ws_registered"

PANEL_URL_PATH = "inkview"
PANEL_TITLE = "InkView"
PANEL_ICON = "mdi:lightning-bolt"
PANEL_MODULE_URL = f"{URL_PREFIX}/panel/inkview-panel.js"

SERVICE_REFRESH = "refresh"
SERVICE_ROTATE_SECRET = "rotate_secret"
SERVICE_REVOKE_ALL_TOKENS = "revoke_all_tokens"
SERVICE_EXTEND_LINK = "extend_link"

ISSUE_NO_ENERGY_SENSORS = "no_energy_sensors"
# Per-entry issues, suffixed with the entry id.
ISSUE_LINK_EXPIRING = "link_expiring"
ISSUE_LINK_EXPIRED = "link_expired"

ENERGY_PERIODS = ("today", "week", "month", "year")
