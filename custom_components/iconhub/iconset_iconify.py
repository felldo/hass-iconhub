import asyncio
import aiohttp
import zipfile
import json
import os
import random
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .iconset_base import IconSetCollection, IconData, IconSetInfo, IconListItem

from .const import DOMAIN, icon_dir


LOGGER = logging.getLogger(__name__)

ICONIFY_REPO_URL = "https://github.com/iconify/icon-sets/archive/refs/heads/master.zip"
ICONIFY_REPO_FILENAME = "iconify-icon-sets-master.zip"


DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=None, connect=30, sock_read=60)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def _load_file(path: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def _load_json(path: zipfile.Path) -> dict:
    with path.open() as fp:
        return json.load(fp)


def _finish_download(tmp: str, target: str):
    if not zipfile.is_zipfile(tmp):
        raise ValueError("Downloaded Iconify archive is not a valid zip file")
    # Atomic: a failed or interrupted download never replaces a working archive
    os.replace(tmp, target)


def _remove_file(path: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


async def download_data(hass: HomeAssistant, force: bool = False):

    targetpath = icon_dir(hass)
    target = os.path.join(targetpath, ICONIFY_REPO_FILENAME)

    if not force:
        exists = await hass.async_add_executor_job(os.path.isfile, target)
        return target if exists else None

    session = async_get_clientsession(hass)
    tmp = target + ".part"

    try:
        async with session.get(ICONIFY_REPO_URL, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()
            # Streamed to disk - the archive is far too large to buffer in memory
            fp = await hass.async_add_executor_job(open, tmp, "wb")
            try:
                async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                    await hass.async_add_executor_job(fp.write, chunk)
            finally:
                await hass.async_add_executor_job(fp.close)
        await hass.async_add_executor_job(_finish_download, tmp, target)
    except BaseException:
        await hass.async_add_executor_job(_remove_file, tmp)
        raise

    return target


def _resolve_icon(datafile: dict, name: str) -> dict | None:
    """Find an icon by name, following alias chains (aliases -> parent)."""
    icons = datafile.get("icons", {})
    aliases = datafile.get("aliases", {})

    chain = []
    while name not in icons:
        alias = aliases.get(name)
        if not alias or len(chain) > 36:  # Unknown name or circular aliases
            return None
        chain.append(alias)
        name = alias.get("parent")

    result = dict(icons[name])
    # Apply transformations from the alias closest to the parent outwards
    for alias in reversed(chain):
        for key, value in alias.items():
            if key == "parent":
                continue
            if key == "rotate":
                result["rotate"] = (result.get("rotate", 0) + value) % 4
            elif key in ("hFlip", "vFlip"):
                result[key] = result.get(key, False) != value
            else:
                result[key] = value
    return result


def _icon_data(datafile: dict, icon: str) -> IconData | None:
    resolved = _resolve_icon(datafile, icon)
    if not resolved:
        return None

    icon_data = {
        "renderer": "iconify",
        "left": datafile.get("left", 0),
        "top": datafile.get("top", 0),
        "width": datafile.get("width", 16),
        "height": datafile.get("height", 16),
        "rotate": datafile.get("rotate", 0),
        "vFlip": datafile.get("vFlip", False),
        "hFlip": datafile.get("hFlip", False),
    }
    icon_data.update(resolved)
    return icon_data


async def _get_data_files(hass: HomeAssistant) -> zipfile.Path:

    path = await download_data(hass)
    if not path:
        return None

    loop = asyncio.get_running_loop()
    zf = await loop.run_in_executor(None, _load_file, path)
    data = zipfile.Path(zf) / "icon-sets-master" / "json"

    return data


class IconifySets(IconSetCollection):

    def __init__(self):
        self.cache: dict[str, IconSetInfo] = {}
        self.prefix_cache = None
        self.data_cache: dict = {}

    def flush(self) -> None:
        self.cache = {}
        self.prefix_cache = None
        self.data_cache = {}

    async def data(self, hass, prefix="/"):
        # Icon set files can be several MB (material-symbols is ~9 MB) and were
        # read and parsed inside the event loop, freezing Home Assistant while
        # it happened. They are now loaded in the executor. The cache holds the
        # loading task, so concurrent requests for the same set (the frontend
        # now fetches icons in parallel) share one load instead of parsing the
        # same file several times. A failed load is removed so it can be retried.
        if not prefix in self.data_cache:
            self.data_cache[prefix] = hass.async_create_task(
                self._load_data(hass, prefix)
            )
        task = self.data_cache[prefix]
        try:
            return await asyncio.shield(task)
        except Exception:
            # Only drop our own task - a flush may already have replaced it
            if self.data_cache.get(prefix) is task:
                self.data_cache.pop(prefix, None)
            raise

    async def _load_data(self, hass, prefix):
        if prefix == "/":
            return await _get_data_files(hass)
        root = await self.data(hass)
        if not root:
            return None
        return await hass.async_add_executor_job(
            _load_json, root / f"{prefix}.json"
        )

    async def sets(self, hass: HomeAssistant) -> dict[str, IconSetInfo]:

        if self.cache:
            return self.cache

        config = hass.config_entries.async_entries(DOMAIN)
        config = config[0] if config else {}

        data = await self.data(hass)
        if not data:
            return {}
        for f in data.iterdir():
            # Parse in the executor, see data()
            js = await hass.async_add_executor_job(_load_json, f)

            prefix = js["prefix"]

            samples = js.get("info", {}).get("samples", [])
            if not samples:
                icons = list(js.get("icons", {}).keys())
                if len(icons):
                    samples = random.sample(icons, min(6, len(icons)))
            # Built from the already loaded file. Going through self.icon()
            # would load every set a second time and keep all of them in
            # data_cache, i.e. in memory, until the next restart.
            samples = [_icon_data(js, icon) for icon in samples]

            self.cache[prefix] = {
                **js.get("info", {}),
                "prefix": prefix,
                "active": config.data.get(prefix, False),
                "sample_icons": samples,
            }

        return self.cache

    async def prefixes(self, hass: HomeAssistant) -> list[str]:

        if self.prefix_cache:
            return self.prefix_cache
        data = await self.data(hass)
        if not data:
            return []

        config = hass.config_entries.async_entries(DOMAIN)
        config = config[0] if config else {}

        self.prefix_cache = []
        for prefix in config.data:
            if data.joinpath(prefix + ".json").is_file():
                self.prefix_cache.append(prefix)

        return self.prefix_cache

    async def list(self, hass: HomeAssistant, prefix: str) -> list[IconListItem]:

        datafile = await self.data(hass, prefix)

        if not datafile:
            return []

        return [{"name": k} for k in datafile.get("icons", {}).keys()]

    async def icon(
        self, hass: HomeAssistant, prefix: str, icon: str
    ) -> IconData | None:

        datafile = await self.data(hass, prefix)

        if not datafile:
            return None

        return _icon_data(datafile, icon)
