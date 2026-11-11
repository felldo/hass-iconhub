import asyncio
import json
import os
import random
import logging
from collections import defaultdict

from homeassistant.core import HomeAssistant

from .iconset_base import IconSetCollection, IconData, IconSetInfo, IconListItem



LOGGER = logging.getLogger(__name__)

FONTAWESOME_FILENAME = "fontawesome.json"
PREPREFIX = "fapro-"


def get_data_file(icon_dir: str) -> dict:
    filepath = os.path.join(icon_dir, FONTAWESOME_FILENAME)
    try:
        with open(filepath) as fp:
            js = json.loads(fp.read())
        return js
    except FileNotFoundError:
        return None


def _load_icons(icon_dir: str) -> dict | None:
    """Read fontawesome.json once and keep only what is needed.

    Returns {"lists": {style: [IconListItem]}, "svgs": {style: {name: svg}}}.
    The metadata file is large, so everything else in it (unicode values,
    labels, changes, ...) is dropped instead of being kept in memory.
    """
    datafile = get_data_file(icon_dir)
    if not datafile:
        return None

    lists = defaultdict(list)
    svgs = defaultdict(dict)
    for name, v in datafile.items():
        for style in v.get("styles", []):
            lists[style].append(
                {
                    "name": name,
                    "keywords": list(map(str, v.get("search", {}).get("terms", []))),
                }
            )
        for style, svg in v.get("svg", {}).items():
            svgs[style][name] = svg
    return {"lists": dict(lists), "svgs": dict(svgs)}


class FontawesomeSets(IconSetCollection):

    def __init__(self, icon_dir: str):
        self.icon_dir = icon_dir
        self.cache: dict[str, IconSetInfo] = {}
        self.data_task: asyncio.Future | None = None

    def flush(self) -> None:
        self.cache = {}
        self.data_task = None

    async def data(self, hass: HomeAssistant) -> dict | None:
        # Previously the whole fontawesome.json was read and parsed again for
        # every single icon. With the frontend loading icons in parallel that
        # meant many full parses at once. Now it is loaded once, and concurrent
        # requests share the same loading task.
        if self.data_task is None:
            self.data_task = hass.async_add_executor_job(_load_icons, self.icon_dir)
        task = self.data_task
        try:
            return await asyncio.shield(task)
        except Exception:
            if self.data_task is task:
                self.data_task = None
            raise

    async def sets(self, hass: HomeAssistant) -> dict[str, IconSetInfo]:

        if self.cache:
            return self.cache

        data = await self.data(hass)
        if not data:
            return {}

        for k, v in data["lists"].items():
            prefix = PREPREFIX + k

            samples = random.sample(v, min(6, len(v)))
            samples = [await self.icon(hass, prefix, icon["name"]) for icon in samples]

            self.cache[prefix] = {
                "name": f"Fontawesome {k}",
                "prefix": prefix,
                "total": len(v),
                "sample_icons": samples,
            }

        return self.cache

    async def prefixes(self, hass: HomeAssistant) -> list[str]:
        data = await self.data(hass)
        if not data:
            return []
        return [PREPREFIX + style for style in data["lists"]]

    async def list(self, hass: HomeAssistant, prefix: str) -> list[IconListItem]:

        style = prefix.removeprefix(PREPREFIX)

        data = await self.data(hass)

        if not data:
            return []

        return data["lists"].get(style, [])

    async def icon(
        self, hass: HomeAssistant, prefix: str, icon: str
    ) -> IconData | None:

        style = prefix.removeprefix(PREPREFIX)

        data = await self.data(hass)

        if not data:
            return None

        svg = data["svgs"].get(style, {}).get(icon)
        if not svg:
            return None

        path = svg.get("path")
        path2 = None
        if isinstance(path, list):
            path, path2 = path

        icon_data = {
            "renderer": None,
            "viewBox": svg.get("viewBox"),
            "path": path,
            "path2": path2,
            "body": svg.get("raw"),
        }

        return icon_data
