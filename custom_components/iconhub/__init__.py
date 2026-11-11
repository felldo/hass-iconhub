import logging
import os

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, ICON_PATH, LEGACY_ICON_PATH
from .frontend import (
    async_add_entry_frontend,
    async_register_frontend,
    async_remove_entry_frontend,
)
from .runtime import IconHubConfigEntry, IconHubData, enabled_sets

LOGGER = logging.getLogger(__name__)

# Configured through the UI only - no YAML configuration
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _setup_icon_dir(hass: HomeAssistant) -> str:
    new_dir = hass.config.path(ICON_PATH)
    legacy_dir = hass.config.path(LEGACY_ICON_PATH)
    if not os.path.exists(new_dir) and os.path.isdir(legacy_dir):
        LOGGER.info(
            "Using icon directory %s. Rename it to %s to use the new location.",
            legacy_dir,
            new_dir,
        )
        return legacy_dir
    os.makedirs(new_dir, exist_ok=True)
    return new_dir


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Websocket commands and static paths can't be unregistered, so they are
    # registered once here instead of per config entry.
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IconHubConfigEntry) -> bool:
    icon_dir = await hass.async_add_executor_job(_setup_icon_dir, hass)
    data = IconHubData.create(icon_dir)
    # Downloads run as tasks of this entry, so unloading cancels them
    data.iconify.create_task = lambda coro, name: entry.async_create_background_task(
        hass, coro, name
    )
    entry.runtime_data = data

    await async_add_entry_frontend(hass, entry)

    # Fetch enabled Iconify sets that aren't stored yet, without delaying setup
    entry.async_create_background_task(
        hass,
        data.iconify.ensure_downloaded(hass, enabled_sets(entry)),
        "iconhub_iconify_download",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IconHubConfigEntry) -> bool:
    async_remove_entry_frontend(hass, entry)
    return True
