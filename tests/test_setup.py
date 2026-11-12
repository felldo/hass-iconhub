"""Config flow, setup, unload and the icon directory."""

import os

import iconhub
from iconhub import config_flow
from iconhub.const import CONF_ENABLED_SETS, DEFAULT_ENABLED_SETS

from conftest import HA, ConfigEntryState, FakeEntry, FakeHass


async def test_config_flow_defaults(hass):
    flow = config_flow.IconHubConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    assert result["options"][CONF_ENABLED_SETS] == DEFAULT_ENABLED_SETS


async def test_config_flow_imports_custom_icons_sets(hass):
    hass.entries["custom_icons"] = [
        FakeEntry(data={"local": True, "mdi-light": True, "fa6-solid": False})
    ]
    flow = config_flow.IconHubConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    assert result["options"][CONF_ENABLED_SETS] == ["local", "mdi-light"]


async def test_setup_registers_once(hass, call):
    assert await iconhub.async_setup(hass, {})
    assert len(HA.commands) == 8
    assert len(HA.static_paths) == 2
    # Without a loaded entry the commands answer cleanly
    assert (await call("ws_get_active_sets")).result == []
    assert (await call("ws_get_icon", set="local", icon="x")).error_code == "not_loaded"


async def test_setup_entry(hass, entry, iconify_dir):
    data = entry.runtime_data
    assert data.js_url in HA.js_urls
    assert data.js_url.startswith("/iconhub/main.js?v=")
    assert [p["frontend_url_path"] for p in HA.panels] == ["iconhub-config"]
    assert HA.panels[0]["module_url"].startswith("/iconhub/panel.js?v=")
    assert os.path.isdir(os.path.join(hass.root, "iconhub"))
    # Enabled Iconify sets are fetched in the background, disabled ones aren't
    assert os.path.isfile(os.path.join(iconify_dir, "collections.json"))
    assert os.path.isfile(os.path.join(iconify_dir, "json", "set-a.json"))
    assert not os.path.exists(os.path.join(iconify_dir, "json", "set-b.json"))


async def test_unload_and_reload(hass, entry, call):
    js_url = entry.runtime_data.js_url
    assert await iconhub.async_unload_entry(hass, entry)
    assert js_url not in HA.js_urls
    assert HA.removed_panels == ["iconhub-config"]

    entry.state = ConfigEntryState.NOT_LOADED
    assert (await call("ws_get_icon", set="local", icon="x")).error_code == "not_loaded"

    # Set up again: panel again, but static paths are not registered twice
    assert await iconhub.async_setup_entry(hass, entry)
    await entry.wait_tasks()
    assert len(HA.panels) == 2
    assert len(HA.static_paths) == 2


async def test_legacy_options_format(hass, entry, call):
    entry.options = {}
    entry.data = {"local": True, "set-a": False}
    assert (await call("ws_get_active_sets")).result == ["local"]


def test_icon_dir_fresh_install(tmp_path):
    path = iconhub._setup_icon_dir(FakeHass(tmp_path))
    assert path == os.path.join(str(tmp_path), "iconhub")
    assert os.path.isdir(path)


def test_icon_dir_reuses_custom_icons(tmp_path):
    os.mkdir(tmp_path / "custom_icons")
    path = iconhub._setup_icon_dir(FakeHass(tmp_path))
    assert path.endswith("custom_icons")
    assert not (tmp_path / "iconhub").exists()


def test_icon_dir_prefers_iconhub(tmp_path):
    os.mkdir(tmp_path / "custom_icons")
    os.mkdir(tmp_path / "iconhub")
    assert iconhub._setup_icon_dir(FakeHass(tmp_path)).endswith("iconhub")
