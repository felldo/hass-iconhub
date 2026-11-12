"""Test setup.

Home Assistant itself is not installed for the tests: the few parts of its
API that IconHub uses are replaced by small stand-ins below. That keeps the
tests fast and runnable on every platform. The stand-ins mirror the
signatures of Home Assistant 2024.7+.
"""

import asyncio
import enum
import json
import os
import sys
import types

import aiohttp
import pytest
from aiohttp import web

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components"))


# ---------------------------------------------------------------- HA stubs

def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


def _identity(func):
    return func


class ConfigEntryState(enum.Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


class ConfigEntry:
    def __class_getitem__(cls, item):
        return cls


class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def async_create_entry(self, **kwargs):
        return kwargs


class HAState:
    """Records what IconHub registered with Home Assistant."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.commands = {}
        self.static_paths = []
        self.panels = []
        self.removed_panels = []
        self.js_urls = set()
        self.session = None


HA = HAState()


async def _register_panel(**kwargs):
    HA.panels.append(kwargs)


_module("homeassistant")
_module("homeassistant.core", HomeAssistant=object, callback=_identity)
_module(
    "homeassistant.config_entries",
    ConfigEntry=ConfigEntry,
    ConfigEntryState=ConfigEntryState,
    ConfigFlow=ConfigFlow,
    ConfigFlowResult=dict,
)
_module("homeassistant.helpers")
_module(
    "homeassistant.helpers.aiohttp_client",
    async_get_clientsession=lambda hass: HA.session,
)
_module(
    "homeassistant.helpers.config_validation",
    config_entry_only_config_schema=lambda domain: None,
)
_module("homeassistant.helpers.typing", ConfigType=dict)
_ws = _module(
    "homeassistant.components.websocket_api",
    websocket_command=lambda schema: _identity,
    async_response=_identity,
    require_admin=_identity,
    ActiveConnection=object,
    async_register_command=lambda hass, f: HA.commands.__setitem__(f.__name__, f),
)
_panel_custom = _module(
    "homeassistant.components.panel_custom", async_register_panel=_register_panel
)
_module("homeassistant.components", panel_custom=_panel_custom, websocket_api=_ws)
_module(
    "homeassistant.components.frontend",
    add_extra_js_url=lambda hass, url: HA.js_urls.add(url),
    remove_extra_js_url=lambda hass, url: HA.js_urls.remove(url),
    async_remove_panel=lambda hass, path, warn_if_unknown=True: HA.removed_panels.append(path),
)
_module(
    "homeassistant.components.http",
    StaticPathConfig=lambda url, path: (url, path),
)


# ---------------------------------------------------------------- fakes

class FakeEntry:
    def __init__(self, data=None, options=None):
        self.data = data or {}
        self.options = options or {}
        self.state = ConfigEntryState.NOT_LOADED
        self.tasks = []

    def async_create_background_task(self, hass, coro, name):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self.tasks.append(task)
        return task

    async def wait_tasks(self):
        await asyncio.gather(*self.tasks, return_exceptions=True)


class FakeHass:
    def __init__(self, root):
        self.root = str(root)
        self.data = {}
        self.entries = {}
        self.config = types.SimpleNamespace(path=lambda *p: os.path.join(self.root, *p))

        async def register_static_paths(paths):
            HA.static_paths.extend(paths)

        self.http = types.SimpleNamespace(async_register_static_paths=register_static_paths)
        hass = self

        class ConfigEntries:
            def async_entries(self, domain=None):
                return hass.entries.get(domain, [])

            def async_update_entry(self, entry, options=None):
                if options is not None:
                    entry.options = options

        self.config_entries = ConfigEntries()

    def async_add_executor_job(self, func, *args):
        return asyncio.get_running_loop().run_in_executor(None, func, *args)


class Connection:
    def __init__(self):
        self.results = []
        self.errors = []

    def send_result(self, msg_id, result=None):
        self.results.append(result)

    def send_error(self, msg_id, code, message):
        self.errors.append((code, message))

    @property
    def result(self):
        assert not self.errors, self.errors
        return self.results[0]

    @property
    def error_code(self):
        assert self.errors, f"expected an error, got {self.results}"
        return self.errors[0][0]


# ---------------------------------------------------------------- fake Iconify

SET_A = {
    "prefix": "set-a",
    "icons": {"a": {"body": "<path d='A'/>", "rotate": 1}},
    "aliases": {
        "b": {"parent": "a", "hFlip": True, "rotate": 2},
        "c": {"parent": "b", "hFlip": True, "rotate": 3, "width": 24},
        "loop1": {"parent": "loop2"},
        "loop2": {"parent": "loop1"},
    },
}
SET_B = {"prefix": "set-b", "icons": {"x": {"body": "<path d='X'/>"}}}
COLLECTIONS = {
    "set-a": {"name": "Set A", "total": 1, "samples": ["a", "b"]},
    "set-b": {"name": "Set B", "total": 1, "samples": ["x"], "palette": True},
    "old-set": {"name": "Old", "total": 1, "hidden": True},
    "../evil": {"name": "Evil"},
}


class IconifyServer:
    """Serves collections.json and json/<prefix>.json like the icon-sets repo.

    mode: "ok", "500" (everything fails), "sets500" / "setsgarbage" (only
    set files fail), "garbage" (invalid JSON everywhere).
    """

    def __init__(self):
        self.requests = []
        self.mode = "ok"
        self.delay = 0
        self.version = 1

    def count(self, name):
        return self.requests.count(name)

    async def handle(self, request):
        name = request.match_info["name"]
        self.requests.append(name)
        if self.delay:
            await asyncio.sleep(self.delay)
        is_set = name != "collections.json"
        if self.mode == "500" or (self.mode == "sets500" and is_set):
            return web.Response(status=500)
        if self.mode == "garbage":
            return web.Response(body=b"{not json")
        if self.mode == "setsgarbage" and is_set:
            return web.Response(body=b"[1, 2]")
        if not is_set:
            return web.json_response(COLLECTIONS)
        sets = {"set-a.json": SET_A, "set-b.json": SET_B, "old-set.json": SET_B}
        if name not in sets:
            return web.Response(status=404)
        data = json.loads(json.dumps(sets[name]))
        data["icons"][f"v{self.version}"] = {"body": ""}
        return web.json_response(data)


# ---------------------------------------------------------------- fixtures

@pytest.fixture
async def iconify_server(monkeypatch):
    from iconhub import iconset_iconify

    server = IconifyServer()
    app = web.Application()
    app.router.add_get("/json/{name}", server.handle)
    app.router.add_get("/{name}", server.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    monkeypatch.setattr(iconset_iconify, "ICONIFY_BASE_URL", f"http://127.0.0.1:{port}")
    yield server
    await runner.cleanup()


@pytest.fixture
async def hass(tmp_path):
    HA.reset()
    HA.session = aiohttp.ClientSession()
    yield FakeHass(tmp_path)
    await HA.session.close()


@pytest.fixture
def call(hass):
    """Call a registered websocket command: await call("ws_get_icon", set=..)."""

    async def _call(command, target=None, **msg):
        connection = Connection()
        result = HA.commands[command](target or hass, connection, {"id": 1, **msg})
        if asyncio.iscoroutine(result):
            await result
        return connection

    return _call


@pytest.fixture
async def entry(hass, iconify_server):
    """A loaded IconHub entry with "local" and "set-a" enabled."""
    import iconhub
    from iconhub.const import CONF_ENABLED_SETS

    await iconhub.async_setup(hass, {})
    config_entry = FakeEntry(options={CONF_ENABLED_SETS: ["local", "set-a"]})
    hass.entries["iconhub"] = [config_entry]
    assert await iconhub.async_setup_entry(hass, config_entry)
    config_entry.state = ConfigEntryState.LOADED
    await config_entry.wait_tasks()
    yield config_entry
    await config_entry.wait_tasks()


@pytest.fixture
def iconify_dir(hass):
    return os.path.join(hass.root, "iconhub", "iconify")
