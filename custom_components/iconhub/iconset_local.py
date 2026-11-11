import asyncio
import os
import logging
import random
from xml.parsers.expat import ExpatError
from homeassistant.core import HomeAssistant

from .iconset_base import (
    IconSetCollection,
    IconData,
    IconSetInfo,
    IconListItem,
    process_svg,
)
from .const import DOMAIN, icon_dir

LOGGER = logging.getLogger(__name__)


def list_icons(root):
    icon_list = []
    for dirpath, dirnames, filenames in os.walk(root):
        subdir = dirpath.removeprefix(root).lstrip("/")
        icon_list.extend(
            [
                {"name": os.path.join(subdir, fn.removesuffix(".svg"))}
                for fn in filenames
                if fn.endswith(".svg") and not fn.endswith("-webfont.svg")
            ]
        )
    return icon_list


def read_icon(path: str) -> str:
    with open(path) as fp:
        return fp.read()


class LocalSet(IconSetCollection):

    def __init__(self):
        self.cache = []

    def flush(self) -> None:
        self.cache = []

    async def sets(self, hass: HomeAssistant) -> dict[str, IconSetInfo]:
        prefix = "local"
        icons = await self.list(hass, prefix)

        config = hass.config_entries.async_entries(DOMAIN)
        config = config[0] if config else {}

        samples = random.sample(icons, min(6, len(icons)))
        samples = [await self.icon(hass, prefix, icon["name"]) for icon in samples]

        return {
            prefix: {
                "name": "Local",
                "prefix": prefix,
                "total": len(icons),
                "active": config.data.get(prefix, False),
                "sample_icons": samples,
            }
        }

    async def prefixes(self, hass: HomeAssistant) -> list[str]:
        return ["local"]

    async def list(self, hass: HomeAssistant, prefix: str) -> list[IconListItem]:
        if self.cache:
            return self.cache

        icon_path = icon_dir(hass)

        loop = asyncio.get_running_loop()

        icons = await loop.run_in_executor(None, list_icons, icon_path)

        self.cache.extend(icons)

        return self.cache

    async def icon(
        self, hass: HomeAssistant, prefix: str, icon: str
    ) -> IconData | None:

        # abspath (not realpath), so symlinks placed in the icon directory on
        # purpose keep working, while "..", and absolute names are rejected.
        root = os.path.abspath(icon_dir(hass))
        icon_path = os.path.abspath(os.path.join(root, icon + ".svg"))

        # The icon name comes from the websocket API, which any logged in user
        # can call. Without this check "local:../../something" could read any
        # .svg file on the system.
        try:
            inside = os.path.commonpath([root, icon_path]) == root
        except ValueError:  # Different drives (Windows)
            inside = False
        if not inside:
            LOGGER.warning("Refusing to load local icon outside %s: %s", root, icon)
            return None

        loop = asyncio.get_running_loop()
        try:
            svg = await loop.run_in_executor(None, read_icon, icon_path)
            return process_svg(svg)
        except (OSError, ExpatError, IndexError) as err:
            # Missing file, unreadable file or not a valid SVG
            LOGGER.debug("Could not load local icon %s: %s", icon, err)
            return None
