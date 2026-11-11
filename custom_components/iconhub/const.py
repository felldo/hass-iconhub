DOMAIN = "iconhub"

ICON_PATH = "iconhub"
# Directory used before the rename from "Custom Icons". Still used when it
# exists and the new directory doesn't, so existing icons keep working.
LEGACY_ICON_PATH = "custom_icons"


def icon_dir(hass) -> str:
    """Absolute path of the icon directory (resolved during setup)."""
    return hass.data.get(DOMAIN, {}).get("icon_dir") or hass.config.path(ICON_PATH)
