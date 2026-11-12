"""Local icons, Fontawesome Pro and webfonts."""

import asyncio
import json
import os

import pytest

from iconhub import iconset_fapro, iconset_webfont
from iconhub.const import CONF_ENABLED_SETS


@pytest.fixture
def icon_dir(hass, entry):
    path = entry.runtime_data.icon_dir
    os.makedirs(os.path.join(path, "sub"), exist_ok=True)
    with open(os.path.join(path, "home.svg"), "w") as fp:
        fp.write("<svg viewBox='0 0 24 24'><path d='M0'/></svg>")
    with open(os.path.join(path, "sub", "deep.svg"), "w") as fp:
        fp.write("<svg viewBox='0 0 24 24'><path d='M1'/></svg>")
    with open(os.path.join(path, "broken.svg"), "w") as fp:
        fp.write("<svg><no")
    with open(os.path.join(hass.root, "secret.svg"), "w") as fp:
        fp.write("<svg viewBox='0 0 1 1'><path d='S'/></svg>")
    return path


async def test_local_icons(icon_dir, call):
    assert (await call("ws_get_icon", set="local", icon="home")).result["path"] == "M0"
    assert (await call("ws_get_icon", set="local", icon="sub/deep")).result["path"] == "M1"
    names = {i["name"] for i in (await call("ws_get_icon_list", set="local")).result}
    assert {"home", "broken"} <= names


@pytest.mark.parametrize(
    "name", ["../secret", "sub/../../secret", "ABSOLUTE", "broken", "missing"]
)
async def test_local_rejects_outside_and_invalid(hass, icon_dir, call, name):
    if name == "ABSOLUTE":
        name = os.path.join(hass.root, "secret")
    assert (await call("ws_get_icon", set="local", icon=name)).error_code == "not_found"


async def test_disabled_local_set(icon_dir, entry, call):
    entry.options = {CONF_ENABLED_SETS: []}
    assert (await call("ws_get_icon", set="local", icon="home")).errors
    assert (await call("ws_get_icon_list", set="local")).result == []
    assert (await call("ws_get_cached_icons", set="local")).result == []


async def test_fontawesome_and_webfont_parsed_once(icon_dir, entry, call, monkeypatch):
    fa = {
        f"i{n}": {
            "styles": ["solid"],
            "search": {"terms": ["t"]},
            "svg": {"solid": {"viewBox": [0, 0, 1, 1], "path": f"P{n}", "raw": "<svg/>"}},
        }
        for n in range(3)
    }
    fa["duo"] = {
        "styles": ["duotone"],
        "svg": {"duotone": {"viewBox": [0, 0, 1, 1], "path": ["P1", "P2"], "raw": "<svg/>"}},
    }
    with open(os.path.join(icon_dir, "fontawesome.json"), "w") as fp:
        json.dump(fa, fp)
    with open(os.path.join(icon_dir, "rpg-webfont.svg"), "w") as fp:
        fp.write(
            "<svg><defs><font id='rpg' horiz-adv-x='512'>"
            "<glyph glyph-name='sword' d='M1'/><glyph glyph-name='shield' d='M2'/>"
            "<glyph d='M3'/></font></defs></svg>"
        )

    counts = {"fa": 0, "webfont": 0}
    load_fa, load_webfont = iconset_fapro._load_icons, iconset_webfont._load_fonts

    def counting_fa(path):
        counts["fa"] += 1
        return load_fa(path)

    def counting_webfont(path):
        counts["webfont"] += 1
        return load_webfont(path)

    monkeypatch.setattr(iconset_fapro, "_load_icons", counting_fa)
    monkeypatch.setattr(iconset_webfont, "_load_fonts", counting_webfont)
    entry.runtime_data.flush()
    entry.options = {CONF_ENABLED_SETS: ["fapro-solid", "fapro-duotone", "rpg"]}

    results = await asyncio.gather(
        *[call("ws_get_icon", set="fapro-solid", icon=f"i{n % 3}") for n in range(20)],
        *[call("ws_get_icon", set="rpg", icon="sword") for _ in range(10)],
    )
    assert all(r.results for r in results)
    assert counts == {"fa": 1, "webfont": 1}

    duo = (await call("ws_get_icon", set="fapro-duotone", icon="duo")).result
    assert (duo["path"], duo["path2"]) == ("P1", "P2")
    sword = (await call("ws_get_icon", set="rpg", icon="sword")).result
    assert sword["path"] == "M1" and sword["viewBox"] == [0, 0, 512, 512]
    names = [i["name"] for i in (await call("ws_get_icon_list", set="rpg")).result]
    assert names == ["sword", "shield"]

    sets = (await call("ws_get_icon_sets")).result
    assert sets["fapro-duotone"]["total"] == 1, "styles with fewer than 6 icons work"
    assert sets["rpg"]["total"] == 2
