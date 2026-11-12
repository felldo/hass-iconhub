"""Iconify: per-set downloads, updates, aliases and prefix validation."""

import asyncio
import os

import aiohttp
import pytest

from iconhub.const import CONF_ENABLED_SETS


def _set_file(iconify_dir, prefix):
    return os.path.join(iconify_dir, "json", f"{prefix}.json")


def _no_temp_files(iconify_dir):
    return not any(f.endswith(".part") for f in os.listdir(os.path.join(iconify_dir, "json")))


async def test_listing_sets_downloads_nothing(entry, call, iconify_server):
    before = len(iconify_server.requests)
    sets = (await call("ws_get_icon_sets")).result
    assert len(iconify_server.requests) == before
    assert {"set-a", "set-b", "local"} <= set(sets)
    assert "old-set" not in sets, "hidden sets are only listed while enabled"
    assert "../evil" not in sets, "invalid prefixes are ignored"
    assert sets["set-a"]["active"] and not sets["set-b"]["active"]
    assert sets["set-a"]["sample_names"] == ["a", "b"]
    assert sets["set-b"]["palette"]


@pytest.mark.parametrize(
    ("name", "rotate", "h_flip", "width"),
    [("a", 1, False, None), ("b", 3, True, None), ("c", 2, False, 24)],
)
async def test_aliases(entry, call, name, rotate, h_flip, width):
    icon = (await call("ws_get_icon", set="set-a", icon=name)).result
    assert icon["body"] == "<path d='A'/>"
    assert icon["rotate"] == rotate
    assert icon["hFlip"] is h_flip
    if width:
        assert icon["width"] == width


@pytest.mark.parametrize("name", ["loop1", "unknown"])
async def test_unknown_or_circular_icon(entry, call, name):
    assert (await call("ws_get_icon", set="set-a", icon=name)).error_code == "not_found"


async def test_disabled_set_is_not_served(entry, call):
    connection = await call("ws_get_icon", set="set-b", icon="x")
    assert "not enabled" in connection.errors[0][1]


async def test_enable_downloads_set(entry, call, iconify_server):
    assert (await call("ws_select_icon_set", set="set-b", active=True)).results
    assert "set-b" in entry.options[CONF_ENABLED_SETS]
    assert iconify_server.count("set-b.json") == 1


async def test_parallel_requests_share_one_download(entry, call, iconify_server):
    entry.options = {CONF_ENABLED_SETS: ["set-b"]}
    iconify_server.delay = 0.2
    results = await asyncio.gather(
        *[call("ws_get_icon", set="set-b", icon="x") for _ in range(20)]
    )
    assert all(r.results for r in results)
    assert iconify_server.count("set-b.json") == 1


async def test_select_rejects_unknown_and_invalid(entry, call):
    assert (await call("ws_select_icon_set", set="nope", active=True)).error_code == "not_found"
    assert (await call("ws_select_icon_set", set="../evil", active=True)).errors
    assert "../evil" not in entry.options[CONF_ENABLED_SETS]


async def test_failed_download_keeps_set_disabled(entry, call, iconify_server, iconify_dir):
    iconify_server.mode = "500"
    connection = await call("ws_select_icon_set", set="set-b", active=True)
    assert connection.error_code == "download_failed"
    assert "set-b" not in entry.options[CONF_ENABLED_SETS]
    assert _no_temp_files(iconify_dir)

    iconify_server.mode = "ok"
    assert (await call("ws_select_icon_set", set="set-b", active=True)).results


async def test_disable_frees_memory(entry, call):
    await call("ws_select_icon_set", set="set-b", active=True)
    await call("ws_get_icon", set="set-b", icon="x")
    assert "set-b" in entry.runtime_data.iconify._sets

    await call("ws_select_icon_set", set="set-b", active=False)
    assert "set-b" not in entry.options[CONF_ENABLED_SETS]
    assert "set-b" not in entry.runtime_data.iconify._sets
    assert "set-b" not in entry.runtime_data.icon_cache


async def test_update_uses_new_version(entry, call, iconify_server):
    assert (await call("ws_get_icon", set="set-a", icon="v1")).results
    iconify_server.version = 2
    assert (await call("ws_update_iconify_sets")).results
    assert (await call("ws_get_icon", set="set-a", icon="v2")).results


@pytest.mark.parametrize("mode", ["500", "garbage", "sets500", "setsgarbage"])
async def test_failed_update_keeps_files(entry, call, iconify_server, iconify_dir, mode):
    before = open(_set_file(iconify_dir, "set-a"), "rb").read()
    iconify_server.mode = mode
    connection = await call("ws_update_iconify_sets")
    assert connection.error_code == "download_failed"
    if mode.startswith("sets"):
        assert "set-a" in connection.errors[0][1], "the failed set is named"
    assert open(_set_file(iconify_dir, "set-a"), "rb").read() == before
    assert _no_temp_files(iconify_dir)

    iconify_server.mode = "ok"
    assert (await call("ws_get_icon", set="set-a", icon="a")).results


async def test_undownloadable_set_gives_clean_error(entry, call, iconify_server):
    entry.options = {CONF_ENABLED_SETS: ["set-b"]}
    iconify_server.mode = "sets500"
    assert (await call("ws_get_icon", set="set-b", icon="x")).error_code == "unavailable"
    iconify_server.mode = "ok"
    assert (await call("ws_get_icon", set="set-b", icon="x")).results


async def test_prefix_validation(hass, entry):
    iconify = entry.runtime_data.iconify
    assert await iconify.data(hass, "../../etc") is None
    assert await iconify.data(hass, "UPPER") is None
    with pytest.raises(ValueError):
        await iconify.download_set(hass, "not-listed")


async def test_aiohttp_is_not_modified(entry, call):
    await call("ws_update_iconify_sets")
    assert aiohttp.ClientSession.__name__ == "ClientSession"
