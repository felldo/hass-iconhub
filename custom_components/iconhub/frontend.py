import hashlib
import logging
import os

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.frontend import (
    add_extra_js_url,
    async_remove_panel,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import CONF_ENABLED_SETS, DOMAIN, PANEL_URL_PATH
from .runtime import IconHubConfigEntry, enabled_sets, get_loaded_entry

LOGGER = logging.getLogger(__name__)

LOADER_URL = f"/{DOMAIN}/main.js"
LOADER_JS = os.path.join(os.path.dirname(__file__), "loader.js")

PANEL_URL = f"/{DOMAIN}/panel.js"
PANEL_JS = os.path.join(os.path.dirname(__file__), "panel.js")


def _file_hash(path: str) -> str:
    with open(path, "rb") as fp:
        return hashlib.md5(fp.read()).hexdigest()[:8]


def _entry_or_error(hass, connection, msg) -> IconHubConfigEntry | None:
    entry = get_loaded_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "IconHub is not set up")
    return entry


def _is_active(entry: IconHubConfigEntry, prefix: str) -> bool:
    """Only icon sets enabled in the configuration panel are served."""
    return prefix in enabled_sets(entry)


async def _all_sets(hass: HomeAssistant, entry: IconHubConfigEntry) -> dict:
    data = entry.runtime_data
    active = enabled_sets(entry)
    result = {}
    for collection in data.collections:
        try:
            sets = await collection.sets(hass)
        except Exception as err:
            # One unavailable source (e.g. Iconify while offline) must not
            # hide all other icon sets
            LOGGER.warning("Could not list icon sets of %s: %s", collection, err)
            continue
        for prefix, info in sets.items():
            is_active = prefix in active
            if info.get("hidden") and not is_active:
                continue  # Deprecated Iconify sets, unless still in use
            result[prefix] = {**info, "active": is_active}
    return result


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/sets"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_get_icon_sets(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Get list of all available icon sets"""
    if entry := _entry_or_error(hass, connection, msg):
        connection.send_result(msg["id"], await _all_sets(hass, entry))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/activesets"})
@callback
def ws_get_active_sets(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Get the list of activated icon sets"""
    entry = get_loaded_entry(hass)
    connection.send_result(msg["id"], enabled_sets(entry) if entry else [])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/select",
        vol.Required("set"): str,
        vol.Required("active"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_select_icon_set(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Enable or disable an icon set"""
    if not (entry := _entry_or_error(hass, connection, msg)):
        return
    prefix = msg["set"]
    data = entry.runtime_data

    if prefix not in await _all_sets(hass, entry):
        connection.send_error(msg["id"], "not_found", f"Unknown icon set {prefix}")
        return

    if msg["active"] and prefix in await data.iconify.prefixes(hass):
        # Enabling an Iconify set downloads it. Done before saving, so a set
        # that can't be downloaded isn't left enabled without icons.
        try:
            await data.iconify.data(hass, prefix)
        except Exception as err:
            LOGGER.error("Downloading Iconify set %s failed: %s", prefix, err)
            connection.send_error(msg["id"], "download_failed", str(err))
            return

    sets = [s for s in enabled_sets(entry) if s != prefix]
    if msg["active"]:
        sets.append(prefix)
    else:
        # Free the memory of the parsed set (up to several MB)
        data.iconify.forget(prefix)
        data.icon_cache.pop(prefix, None)
    # No update listener: changing the options must not reload the entry
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ENABLED_SETS: sets}
    )
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/list", vol.Required("set"): str}
)
@websocket_api.async_response
async def ws_get_icon_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Get the list of icons in a set"""
    prefix = msg["set"]
    entry = get_loaded_entry(hass)
    if not entry or not _is_active(entry, prefix):
        connection.send_result(msg["id"], [])
        return

    for collection in entry.runtime_data.collections:
        if prefix in await collection.prefixes(hass):
            connection.send_result(msg["id"], await collection.list(hass, prefix))
            return
    connection.send_result(msg["id"], [])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/icon",
        vol.Required("set"): str,
        vol.Required("icon"): str,
    }
)
@websocket_api.async_response
async def ws_get_icon(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Get an icon"""
    prefix = msg["set"]
    icon = msg["icon"]

    if not (entry := _entry_or_error(hass, connection, msg)):
        return
    if not _is_active(entry, prefix):
        connection.send_error(
            msg["id"], "not_found", f"Icon set {prefix} is not enabled"
        )
        return

    icon_cache = entry.runtime_data.icon_cache
    icn = icon_cache[prefix].get(icon)
    if icn is None:
        for collection in entry.runtime_data.collections:
            if prefix in await collection.prefixes(hass):
                try:
                    icn = await collection.icon(hass, prefix, icon)
                except Exception as err:
                    # E.g. an enabled Iconify set that can't be downloaded
                    LOGGER.debug("Could not load icon %s:%s: %s", prefix, icon, err)
                    connection.send_error(msg["id"], "unavailable", str(err))
                    return
                if icn is not None:
                    icn.update({"prefix": prefix, "icon": icon})
                    icon_cache[prefix][icon] = icn
                    break

    if icn is None:
        connection.send_error(
            msg["id"], "not_found", f"Icon {prefix}:{icon} not found"
        )
        return

    connection.send_result(msg["id"], icn)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/icon_cache",
        vol.Required("set"): str,
    }
)
@callback
def ws_get_cached_icons(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Get all cached icons"""
    prefix = msg["set"]
    entry = get_loaded_entry(hass)
    if not entry or not _is_active(entry, prefix):
        connection.send_result(msg["id"], [])
        return
    cache = entry.runtime_data.icon_cache.get(prefix, {})
    connection.send_result(msg["id"], list(cache.values()))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/iconify_update"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_update_iconify_sets(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Refresh the list of Iconify sets and re-download all enabled sets"""
    if not (entry := _entry_or_error(hass, connection, msg)):
        return
    data = entry.runtime_data
    try:
        failed = await data.iconify.update(hass, enabled_sets(entry))
    except Exception as err:
        LOGGER.error("Updating Iconify icon sets failed: %s", err)
        connection.send_error(msg["id"], "download_failed", str(err))
        return
    finally:
        data.flush()

    if failed:
        connection.send_error(
            msg["id"],
            "download_failed",
            f"Could not update: {', '.join(failed)}",
        )
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/flush_icons"})
@websocket_api.require_admin
@callback
def ws_flush_icons(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
):
    """Reload all icons"""
    if entry := _entry_or_error(hass, connection, msg):
        entry.runtime_data.flush()
        connection.send_result(msg["id"])


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register websocket commands and static files. Once per HA run."""
    for command in (
        ws_get_icon_sets,
        ws_get_active_sets,
        ws_select_icon_set,
        ws_get_icon_list,
        ws_get_icon,
        ws_get_cached_icons,
        ws_update_iconify_sets,
        ws_flush_icons,
    ):
        websocket_api.async_register_command(hass, command)

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(LOADER_URL, LOADER_JS),
            StaticPathConfig(PANEL_URL, PANEL_JS),
        ]
    )


async def async_add_entry_frontend(
    hass: HomeAssistant, entry: IconHubConfigEntry
) -> None:
    """Load the icon loader in the frontend and add the configuration panel."""
    # The loader is served with a long cache lifetime, so the URL carries a
    # content hash. Otherwise browsers, the companion apps and proxies such as
    # Cloudflare keep using an old loader after an update.
    loader_hash = await hass.async_add_executor_job(_file_hash, LOADER_JS)
    panel_hash = await hass.async_add_executor_job(_file_hash, PANEL_JS)
    entry.runtime_data.js_url = f"{LOADER_URL}?v={loader_hash}"
    add_extra_js_url(hass, entry.runtime_data.js_url)

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=PANEL_URL_PATH,
        config_panel_domain=DOMAIN,
        webcomponent_name="iconhub-panel",
        module_url=f"{PANEL_URL}?v={panel_hash}",
        embed_iframe=False,
        require_admin=True,
    )


@callback
def async_remove_entry_frontend(
    hass: HomeAssistant, entry: IconHubConfigEntry
) -> None:
    async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    if entry.runtime_data.js_url:
        try:
            remove_extra_js_url(hass, entry.runtime_data.js_url)
        except KeyError:
            pass
