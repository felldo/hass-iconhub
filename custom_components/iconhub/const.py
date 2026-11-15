DOMAIN = "iconhub"

ICON_PATH = "iconhub"
# Directory used before the rename from "Custom Icons". Still used when it
# exists and the new directory doesn't, so existing icons keep working.
LEGACY_ICON_PATH = "custom_icons"
LEGACY_DOMAIN = "custom_icons"

CONF_ENABLED_SETS = "enabled_sets"
DEFAULT_ENABLED_SETS = ["local", "fa6-regular", "fa6-solid", "fa6-brands"]
# Weekly update of the downloaded Iconify sets. Entries without the option
# (created before it existed) count as enabled.
CONF_AUTO_UPDATE = "auto_update"
DEFAULT_AUTO_UPDATE = True
# Days between automatic updates
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 7
MIN_UPDATE_INTERVAL = 1
MAX_UPDATE_INTERVAL = 365

PANEL_URL_PATH = f"{DOMAIN}-config"
