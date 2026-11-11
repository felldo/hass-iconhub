import asyncio
import os
import logging
import random
from xml.dom import minidom
from homeassistant.core import HomeAssistant

from .iconset_base import (
    IconSetCollection,
    IconData,
    IconSetInfo,
    IconListItem,
)
from .const import DOMAIN, icon_dir

LOGGER = logging.getLogger(__name__)


def list_files(root: str):
    set_list = []
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.endswith("-webfont.svg"):
                set_list.append(os.path.join(dirpath, f))

    return set_list


def _load_fonts(root: str) -> dict:
    """Parse all webfont files once.

    Returns {prefix: {"size": int, "glyphs": {glyph-name: path}}}.
    """
    fonts = {}
    for filename in list_files(root):
        try:
            doc = minidom.parse(filename)
        except Exception as err:
            LOGGER.error("Could not parse webfont %s: %s", filename, err)
            continue
        for font in doc.getElementsByTagName("font"):
            prefix = font.getAttribute("id")
            size = (
                int(font.getAttribute("horiz-adv-x"))
                if font.hasAttribute("horiz-adv-x")
                else 1000
            )
            glyphs = {
                g.getAttribute("glyph-name"): g.getAttribute("d")
                for g in font.getElementsByTagName("glyph")
                if g.getAttribute("glyph-name")
            }
            fonts[prefix] = {"size": size, "glyphs": glyphs}
        doc.unlink()
    return fonts


def _process_icon(path, size):
    return {
        "renderer": None,
        "viewBox": [0, 0, size, size],
        "path": path,
        "body": f"""
            <g transform='translate(0, {size}) scale(1, -1)'>
                <path d='{path}' />
            </g>""",
    }


class WebfontSets(IconSetCollection):

    def __init__(self):
        self.data_task: asyncio.Future | None = None

    def flush(self) -> None:
        self.data_task = None

    async def data(self, hass: HomeAssistant) -> dict:
        # Previously the whole webfont file was read and parsed again for every
        # single icon (and for every icon list). Now all fonts are parsed once,
        # and concurrent requests share the same loading task.
        if self.data_task is None:
            self.data_task = hass.async_add_executor_job(
                _load_fonts, icon_dir(hass)
            )
        task = self.data_task
        try:
            return await asyncio.shield(task)
        except Exception:
            if self.data_task is task:
                self.data_task = None
            raise

    async def sets(self, hass: HomeAssistant) -> dict[str, IconSetInfo]:

        config = hass.config_entries.async_entries(DOMAIN)
        config = config[0] if config else {}

        fonts = await self.data(hass)

        sets = {}
        for prefix, font in fonts.items():
            names = list(font["glyphs"].keys())
            samples = random.sample(names, min(6, len(names)))
            sets[prefix] = {
                "name": prefix,
                "prefix": prefix,
                "total": len(names),
                "active": config.data.get(prefix, False),
                "sample_icons": [
                    _process_icon(font["glyphs"][n], font["size"]) for n in samples
                ],
            }

        return sets

    async def prefixes(self, hass: HomeAssistant) -> list[str]:
        return list((await self.data(hass)).keys())

    async def list(self, hass: HomeAssistant, prefix: str) -> list[IconListItem]:
        font = (await self.data(hass)).get(prefix)
        if not font:
            return []
        return [{"name": name} for name in font["glyphs"]]

    async def icon(
        self, hass: HomeAssistant, prefix: str, icon: str
    ) -> IconData | None:
        font = (await self.data(hass)).get(prefix)
        if not font or icon not in font["glyphs"]:
            return None
        return _process_icon(font["glyphs"][icon], font["size"])
