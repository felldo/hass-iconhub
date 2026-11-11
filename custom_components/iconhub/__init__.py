import logging
import os

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, ICON_PATH, LEGACY_ICON_PATH
from .frontend import async_register_iconhub_frontend

LOGGER = logging.getLogger(__name__)

# Configured through the UI only - no YAML configuration
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _setup_icon_dir(hass) -> str:
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


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})["icon_dir"] = await hass.async_add_executor_job(
        _setup_icon_dir, hass
    )

    await async_register_iconhub_frontend(hass)
    return True


async def async_setup_entry(hass, entry):
    return True


async def async_remove_entry(hass, entry):
    return True
