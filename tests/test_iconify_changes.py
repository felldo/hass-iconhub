"""Checking for newer Iconify sets and the changes found by an update."""

import os

from iconhub import iconset_iconify


async def test_check_up_to_date(entry, call):
    result = (await call("ws_check_iconify_sets")).result
    assert result["checked"]
    # Only enabled Iconify sets: not "local", not the disabled set-b
    assert list(result["sets"]) == ["set-a"]
    info = result["sets"]["set-a"]
    assert info["name"] == "Set A"
    assert info["local_version"] == info["remote_version"] == "1.1"
    assert info["local_total"] == info["remote_total"] == 1
    assert info["downloaded"]
    assert info["update_available"] is False


async def test_check_finds_new_version_without_downloading(
    entry, call, iconify_server, iconify_dir
):
    collections = os.path.join(iconify_dir, "collections.json")
    before = open(collections, "rb").read()
    set_requests = iconify_server.count("set-a.json")
    iconify_server.version = 2

    info = (await call("ws_check_iconify_sets")).result["sets"]["set-a"]
    assert info["update_available"] is True
    assert (info["local_version"], info["remote_version"]) == ("1.1", "1.2")
    # Nothing downloaded or stored
    assert iconify_server.count("set-a.json") == set_requests
    assert open(collections, "rb").read() == before


async def test_check_reports_missing_download(entry, call, iconify_dir):
    os.remove(os.path.join(iconify_dir, "json", "set-a.json"))
    info = (await call("ws_check_iconify_sets")).result["sets"]["set-a"]
    assert info["update_available"] is True
    assert info["downloaded"] is None


async def test_check_offline(entry, call, iconify_server):
    iconify_server.mode = "500"
    assert (await call("ws_check_iconify_sets")).error_code == "download_failed"
    iconify_server.mode = "garbage"
    assert (await call("ws_check_iconify_sets")).error_code == "download_failed"


async def test_update_records_new_and_removed_icons(entry, call, iconify_server):
    iconify_server.version = 2
    assert (await call("ws_update_iconify_sets")).results
    status = (await call("ws_get_iconify_status")).result
    changes = status["changes"]["set-a"]
    assert changes["name"] == "Set A"
    assert (changes["old_version"], changes["new_version"]) == ("1.1", "1.2")
    assert changes["added"] == {"count": 1, "names": ["v2"]}
    assert changes["removed"] == {"count": 1, "names": ["v1"]}
    assert changes["changed"] == {"count": 0, "names": []}
    assert status["changes_time"] == status["last_success"]


async def test_update_records_changed_icons(entry, call, iconify_server):
    iconify_server.body_a = "<path d='NEW'/>"
    assert (await call("ws_update_iconify_sets")).results
    changes = (await call("ws_get_iconify_status")).result["changes"]["set-a"]
    # Aliases of "a" only point to it, so only "a" itself changed
    assert changes["changed"] == {"count": 1, "names": ["a"]}
    assert changes["added"]["count"] == changes["removed"]["count"] == 0


async def test_update_without_changes(entry, call):
    assert (await call("ws_update_iconify_sets")).results
    status = (await call("ws_get_iconify_status")).result
    assert status["changes"] == {}
    assert status["changes_time"]


async def test_failed_update_keeps_the_last_changes(entry, call, iconify_server):
    iconify_server.version = 2
    await call("ws_update_iconify_sets")
    iconify_server.mode = "500"
    await call("ws_update_iconify_sets")
    status = (await call("ws_get_iconify_status")).result
    assert status["error"]
    assert "set-a" in status["changes"]


async def test_enabling_a_set_records_no_changes(entry, call):
    await call("ws_select_icon_set", set="set-b", active=True)
    assert (await call("ws_get_iconify_status")).result["changes"] is None


def test_long_name_lists_are_cut():
    old = {"icons": {}}
    new = {"icons": {f"i{n:03}": {"body": ""} for n in range(150)}}
    changes = iconset_iconify._set_changes(old, new)
    assert changes["added"]["count"] == 150
    assert len(changes["added"]["names"]) == iconset_iconify.MAX_CHANGED_NAMES
    assert iconset_iconify._set_changes(new, new) is None
