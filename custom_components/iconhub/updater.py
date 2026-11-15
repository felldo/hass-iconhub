"""Updating the downloaded Iconify icon sets: by hand and every few days.

Downloaded sets are never refreshed on their own otherwise. The automatic
update checks every hour whether the last update is older than the
configured number of days (a week by default), so it also happens when Home
Assistant is restarted often. After a failed update it tries again a day
later instead of every hour.
"""

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_UPDATE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AUTO_UPDATE,
    DEFAULT_UPDATE_INTERVAL,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from .runtime import IconHubConfigEntry, enabled_sets

LOGGER = logging.getLogger(__name__)

RETRY_INTERVAL = timedelta(days=1)
CHECK_INTERVAL = timedelta(hours=1)


def now() -> float:
    return time.time()


def auto_update_enabled(entry: IconHubConfigEntry) -> bool:
    return bool(entry.options.get(CONF_AUTO_UPDATE, DEFAULT_AUTO_UPDATE))


def update_interval(entry: IconHubConfigEntry) -> int:
    """Days between automatic updates."""
    try:
        days = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    except (TypeError, ValueError):
        days = DEFAULT_UPDATE_INTERVAL
    return min(max(days, MIN_UPDATE_INTERVAL), MAX_UPDATE_INTERVAL)


def next_update(status: dict, days: int = DEFAULT_UPDATE_INTERVAL) -> float:
    """When the next automatic update is due (unix time, 0 = now)."""
    interval = timedelta(days=days)
    due = 0.0
    if status.get("last_success"):
        due = status["last_success"] + interval.total_seconds()
    if status.get("error") and status.get("last_attempt"):
        retry = min(RETRY_INTERVAL, interval)
        due = max(due, status["last_attempt"] + retry.total_seconds())
    return due


def update_running(entry: IconHubConfigEntry) -> bool:
    task = entry.runtime_data.update_task
    return task is not None and not task.done()


async def _update(hass: HomeAssistant, entry: IconHubConfigEntry) -> list[str]:
    data = entry.runtime_data
    started = now()
    try:
        failed, changes = await data.iconify.update(hass, enabled_sets(entry))
    except Exception as err:
        await data.iconify.write_status(hass, started, str(err) or repr(err))
        raise
    finally:
        # Icons rendered from the old files must not be served any more
        data.flush()
    error = f"Could not update: {', '.join(failed)}" if failed else None
    await data.iconify.write_status(hass, started, error, changes)
    return failed


async def async_update_iconify(
    hass: HomeAssistant, entry: IconHubConfigEntry
) -> list[str]:
    """Update the list of sets and all enabled sets.

    Returns the sets that failed to update. Raises if the list of sets
    couldn't be downloaded. Calls during a running update wait for it
    instead of starting another one.
    """
    data = entry.runtime_data
    if not update_running(entry):
        # A task of the entry, so unloading the entry cancels it
        data.update_task = entry.async_create_background_task(
            hass, _update(hass, entry), "iconhub_iconify_update"
        )
    # Shielded: a closed websocket connection mustn't cancel the update
    return await asyncio.shield(data.update_task)


async def async_get_status(hass: HomeAssistant, entry: IconHubConfigEntry) -> dict:
    status = await entry.runtime_data.iconify.read_status(hass)
    enabled = auto_update_enabled(entry)
    days = update_interval(entry)
    return {
        **status,
        "auto_update": enabled,
        "update_interval": days,
        "running": update_running(entry),
        "next_update": next_update(status, days) if enabled else None,
    }


async def async_check_iconify(hass: HomeAssistant, entry: IconHubConfigEntry) -> dict:
    """Which enabled sets have a newer version, without downloading them."""
    sets = await entry.runtime_data.iconify.check(hass, enabled_sets(entry))
    return {"checked": now(), "sets": sets}


async def _auto_update(hass: HomeAssistant, entry: IconHubConfigEntry) -> None:
    # Read on every check: changing the option doesn't reload the entry
    if not auto_update_enabled(entry) or update_running(entry):
        return
    status = await entry.runtime_data.iconify.read_status(hass)
    if now() < next_update(status, update_interval(entry)):
        return
    LOGGER.debug("Updating the Iconify icon sets (automatic update)")
    try:
        failed = await async_update_iconify(hass, entry)
    except Exception as err:
        LOGGER.warning("Automatic update of the Iconify icon sets failed: %s", err)
        return
    if failed:
        LOGGER.warning(
            "Automatic update: could not update the Iconify sets %s",
            ", ".join(failed),
        )


@callback
def async_setup_auto_update(hass: HomeAssistant, entry: IconHubConfigEntry) -> None:
    """Check every hour whether the automatic update is due.

    The first check runs an hour after setup, so it never delays the start
    of Home Assistant.
    """

    @callback
    def check(_now=None) -> None:
        entry.async_create_background_task(
            hass, _auto_update(hass, entry), "iconhub_iconify_auto_update"
        )

    entry.async_on_unload(async_track_time_interval(hass, check, CHECK_INTERVAL))
