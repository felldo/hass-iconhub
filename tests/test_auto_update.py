"""Weekly automatic update of the Iconify sets and the update status."""

import asyncio
import time

import pytest

from iconhub import updater
from iconhub.const import CONF_AUTO_UPDATE, CONF_UPDATE_INTERVAL

from conftest import HA

DAY = 24 * 3600


@pytest.fixture
def clock(monkeypatch):
    """updater.now(), moved forward with clock.t += ..."""

    class Clock:
        t = time.time()

    clock = Clock()
    monkeypatch.setattr(updater, "now", lambda: clock.t)
    return clock


async def tick(entry):
    """One run of the hourly check."""
    HA.intervals[-1][1]()
    await entry.wait_tasks()


async def set_last_update(hass, entry, when, error=None):
    await entry.runtime_data.iconify.write_status(hass, when, error)


async def test_timer_checks_every_hour(entry):
    assert len(HA.intervals) == 1
    assert HA.intervals[0][2] == updater.CHECK_INTERVAL


async def test_fresh_download_is_not_updated_again(entry, iconify_server, clock):
    # No status recorded yet: the download at setup counts as the last update
    before = len(iconify_server.requests)
    await tick(entry)
    assert len(iconify_server.requests) == before


async def test_update_after_a_week(hass, entry, call, iconify_server, clock):
    assert (await call("ws_get_icon", set="set-a", icon="v1")).results
    await set_last_update(hass, entry, clock.t - 8 * DAY)
    iconify_server.version = 2

    await tick(entry)
    assert iconify_server.count("collections.json") == 2
    assert iconify_server.count("set-a.json") == 2
    assert iconify_server.count("set-b.json") == 0, "disabled sets aren't downloaded"
    # The icon cache was flushed: the new version is served
    assert (await call("ws_get_icon", set="set-a", icon="v2")).results

    status = (await call("ws_get_iconify_status")).result
    assert status["last_success"] == clock.t
    assert status["error"] is None
    assert status["next_update"] == clock.t + 7 * DAY

    # Not again before the next week
    await tick(entry)
    assert iconify_server.count("set-a.json") == 2


async def test_not_due_within_a_week(hass, entry, iconify_server, clock):
    await set_last_update(hass, entry, clock.t - 6 * DAY)
    await tick(entry)
    assert iconify_server.count("set-a.json") == 1


async def test_disabled_auto_update(hass, entry, call, iconify_server, clock):
    await set_last_update(hass, entry, clock.t - 30 * DAY)
    status = (await call("ws_set_auto_update", enabled=False)).result
    assert entry.options[CONF_AUTO_UPDATE] is False
    assert status["auto_update"] is False and status["next_update"] is None
    assert entry.options["enabled_sets"] == ["local", "set-a"], "other options kept"

    await tick(entry)
    assert iconify_server.count("set-a.json") == 1

    assert (await call("ws_set_auto_update", enabled=True)).result["auto_update"]
    await tick(entry)
    assert iconify_server.count("set-a.json") == 2


async def test_missing_option_means_enabled(hass, entry, iconify_server, clock):
    assert CONF_AUTO_UPDATE not in entry.options
    await set_last_update(hass, entry, clock.t - 8 * DAY)
    await tick(entry)
    assert iconify_server.count("set-a.json") == 2


@pytest.mark.parametrize("mode", ["500", "sets500"])
async def test_failed_update_retries_a_day_later(
    hass, entry, call, iconify_server, clock, mode
):
    last = clock.t - 8 * DAY
    await set_last_update(hass, entry, last)
    iconify_server.mode = mode
    await tick(entry)

    status = (await call("ws_get_iconify_status")).result
    assert status["last_success"] == last, "a failed update isn't a success"
    assert status["last_attempt"] == clock.t
    assert status["error"]
    assert status["next_update"] == clock.t + DAY

    # Not retried every hour
    requests = len(iconify_server.requests)
    clock.t += 3600
    await tick(entry)
    assert len(iconify_server.requests) == requests

    iconify_server.mode = "ok"
    clock.t += DAY
    await tick(entry)
    status = (await call("ws_get_iconify_status")).result
    assert status["error"] is None and status["last_success"] == clock.t


async def test_manual_update_records_status(entry, call, clock):
    assert (await call("ws_update_iconify_sets")).results
    status = (await call("ws_get_iconify_status")).result
    assert status["last_success"] == status["last_attempt"] == clock.t
    assert status["running"] is False


async def test_manual_failure_is_recorded(entry, call, iconify_server, clock):
    iconify_server.mode = "500"
    assert (await call("ws_update_iconify_sets")).error_code == "download_failed"
    status = (await call("ws_get_iconify_status")).result
    assert status["last_attempt"] == clock.t and status["error"]


async def test_concurrent_updates_share_one_download(
    hass, entry, call, iconify_server, clock
):
    await set_last_update(hass, entry, clock.t - 8 * DAY)
    iconify_server.delay = 0.2
    HA.intervals[-1][1]()  # Automatic update starts
    await asyncio.sleep(0.05)
    assert (await call("ws_get_iconify_status")).result["running"]
    connection = await call("ws_update_iconify_sets")
    await entry.wait_tasks()
    assert connection.results
    assert iconify_server.count("set-a.json") == 2  # Setup + one update


async def test_damaged_status_file(hass, entry, call, iconify_dir):
    with open(f"{iconify_dir}/update_status.json", "w") as fp:
        fp.write("{broken")
    status = (await call("ws_get_iconify_status")).result
    assert status["last_success"], "falls back to the time of the set list"


async def test_sets_show_download_time(entry, call):
    sets = (await call("ws_get_icon_sets")).result
    assert sets["set-a"]["downloaded"] > 0
    assert sets["set-b"]["downloaded"] is None


async def test_custom_interval(hass, entry, call, iconify_server, clock):
    status = (await call("ws_set_auto_update", interval=3)).result
    assert entry.options[CONF_UPDATE_INTERVAL] == 3
    assert status["update_interval"] == 3
    assert status["auto_update"] is True, "the switch is left as it was"

    await set_last_update(hass, entry, clock.t - 2 * DAY)
    await tick(entry)
    assert iconify_server.count("set-a.json") == 1

    clock.t += DAY
    await tick(entry)
    assert iconify_server.count("set-a.json") == 2
    status = (await call("ws_get_iconify_status")).result
    assert status["next_update"] == clock.t + 3 * DAY


async def test_default_interval_is_a_week(entry, call):
    status = (await call("ws_get_iconify_status")).result
    assert status["update_interval"] == 7


@pytest.mark.parametrize(("value", "days"), [(0, 1), (9999, 365), ("x", 7), (None, 7)])
def test_stored_interval_is_sanitized(value, days):
    from conftest import FakeEntry

    entry = FakeEntry(options={CONF_UPDATE_INTERVAL: value})
    assert updater.update_interval(entry) == days


def test_retry_never_later_than_interval():
    status = {"last_success": 1000, "last_attempt": 2000, "error": "x"}
    assert updater.next_update(status, 1) == 2000 + DAY
    assert updater.next_update(status, 7) == 1000 + 7 * DAY
