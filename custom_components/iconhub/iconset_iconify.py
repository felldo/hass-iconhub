"""Iconify icon sets, downloaded one set at a time.

Previously the whole iconify/icon-sets repository was downloaded as a zip
archive and every set was read from it. Now only the list of available sets
(collections.json, ~150 kB) and the JSON files of the *enabled* sets are
downloaded and stored in <icon dir>/iconify/.
"""

import asyncio
import json
import logging
import os
import re
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .iconset_base import IconSetCollection, IconData, IconSetInfo, IconListItem

LOGGER = logging.getLogger(__name__)

ICONIFY_BASE_URL = "https://raw.githubusercontent.com/iconify/icon-sets/master"
COLLECTIONS_FILENAME = "collections.json"
ICONIFY_DIRNAME = "iconify"

DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=300, connect=30, sock_read=60)

# Iconify prefixes are lowercase words separated by single dashes. Checked
# before a prefix is used in a URL or file name.
PREFIX_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

TaskFactory = Callable[[Coroutine[Any, Any, Any], str], asyncio.Future]


def valid_prefix(prefix: str) -> bool:
    return bool(PREFIX_RE.match(prefix))


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        return None


def _write_json_atomic(path: str, raw: bytes, required_key: str | None) -> dict:
    """Validate downloaded JSON and replace the file atomically."""
    data = json.loads(raw)
    if not isinstance(data, dict) or (required_key and required_key not in data):
        raise ValueError(f"Unexpected content for {os.path.basename(path)}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    try:
        with open(tmp, "wb") as fp:
            fp.write(raw)
        # A failed download never replaces a working file
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return data


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


class IconifySets(IconSetCollection):

    def __init__(self, icon_dir: str):
        self.dir = os.path.join(icon_dir, ICONIFY_DIRNAME)
        # Creates tasks tied to the config entry (cancelled on unload).
        # Replaced by the integration setup; plain tasks are used otherwise.
        self.create_task: TaskFactory | None = None
        self._collections: asyncio.Future | None = None
        self._sets: dict[str, asyncio.Future] = {}
        self._downloads: dict[str, asyncio.Future] = {}

    def flush(self) -> None:
        # Drops parsed data only. Running downloads are kept and shared.
        self._collections = None
        self._sets = {}

    def forget(self, prefix: str) -> None:
        """Drop the parsed data of one set (e.g. when it is disabled)."""
        self._sets.pop(prefix, None)

    # ---- shared tasks

    def _task(self, coro, name: str) -> asyncio.Future:
        if self.create_task:
            return self.create_task(coro, name)
        return asyncio.get_running_loop().create_task(coro, name=name)

    async def _shared(
        self, cache: dict, key: str, factory, name: str, keep: bool = True
    ):
        """Run factory() once per key; concurrent callers share the result.

        A failed run is forgotten, so the next call tries again. With
        keep=False a finished run is forgotten too (used for downloads, so
        the next call downloads again instead of returning the old result).
        """
        if key not in cache:
            cache[key] = self._task(factory(), name)
        task = cache[key]
        try:
            result = await asyncio.shield(task)
        except Exception:
            if cache.get(key) is task:
                cache.pop(key, None)
            raise
        if not keep and cache.get(key) is task:
            cache.pop(key, None)
        return result

    # ---- downloads

    async def _download(
        self, hass: HomeAssistant, url: str, path: str, required_key: str | None
    ) -> dict:
        session = async_get_clientsession(hass)
        async with session.get(url, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()
            raw = await response.read()
        return await hass.async_add_executor_job(
            _write_json_atomic, path, raw, required_key
        )

    async def _download_collections(self, hass: HomeAssistant) -> dict:
        return await self._shared(
            self._downloads,
            "/collections",
            lambda: self._download(
                hass,
                f"{ICONIFY_BASE_URL}/{COLLECTIONS_FILENAME}",
                os.path.join(self.dir, COLLECTIONS_FILENAME),
                None,
            ),
            "iconhub_download_collections",
            keep=False,
        )

    async def download_set(self, hass: HomeAssistant, prefix: str) -> dict:
        """Download (or update) one icon set."""
        if not valid_prefix(prefix) or prefix not in await self.collections(hass):
            raise ValueError(f"Unknown Iconify icon set: {prefix}")
        data = await self._shared(
            self._downloads,
            prefix,
            lambda: self._download(
                hass,
                f"{ICONIFY_BASE_URL}/json/{prefix}.json",
                self._set_path(prefix),
                "icons",
            ),
            f"iconhub_download_{prefix}",
            keep=False,
        )
        return data

    async def ensure_downloaded(self, hass: HomeAssistant, prefixes: list[str]):
        """Download enabled sets that are missing. Errors are only logged."""
        try:
            available = await self.collections(hass)
        except Exception as err:
            LOGGER.warning("Could not load the list of Iconify icon sets: %s", err)
            return
        for prefix in prefixes:
            if prefix not in available:
                continue
            exists = await hass.async_add_executor_job(
                os.path.isfile, self._set_path(prefix)
            )
            if exists:
                continue
            try:
                await self.download_set(hass, prefix)
            except Exception as err:
                LOGGER.warning("Could not download Iconify set %s: %s", prefix, err)

    async def update(self, hass: HomeAssistant, prefixes: list[str]) -> list[str]:
        """Refresh the set list and re-download the given (enabled) sets.

        Returns the prefixes that failed to update.
        """
        await self._download_collections(hass)
        self._collections = None
        available = await self.collections(hass)
        failed = []
        for prefix in prefixes:
            if prefix not in available:
                continue
            try:
                await self.download_set(hass, prefix)
            except Exception as err:
                LOGGER.warning("Could not update Iconify set %s: %s", prefix, err)
                failed.append(prefix)
            else:
                self._sets.pop(prefix, None)  # Parse the new file on next use
        return failed

    # ---- data

    def _set_path(self, prefix: str) -> str:
        return os.path.join(self.dir, "json", f"{prefix}.json")

    async def collections(self, hass: HomeAssistant) -> dict:
        """All available Iconify sets: {prefix: info}."""

        async def load():
            path = os.path.join(self.dir, COLLECTIONS_FILENAME)
            data = await hass.async_add_executor_job(_read_json, path)
            if data is None:
                data = await self._download_collections(hass)
            return {k: v for k, v in data.items() if valid_prefix(k)}

        if self._collections is None:
            self._collections = self._task(load(), "iconhub_load_collections")
        task = self._collections
        try:
            return await asyncio.shield(task)
        except Exception:
            if self._collections is task:
                self._collections = None
            raise

    async def data(self, hass: HomeAssistant, prefix: str) -> dict | None:
        """Parsed icon set. Downloaded first if it isn't stored yet."""
        if not valid_prefix(prefix):
            return None

        async def load():
            data = await hass.async_add_executor_job(
                _read_json, self._set_path(prefix)
            )
            if data is None:
                data = await self.download_set(hass, prefix)
            return data

        return await self._shared(self._sets, prefix, load, f"iconhub_load_{prefix}")

    # ---- IconSetCollection

    async def sets(self, hass: HomeAssistant) -> dict[str, IconSetInfo]:
        result = {}
        for prefix, info in (await self.collections(hass)).items():
            result[prefix] = {
                **info,
                "prefix": prefix,
                "renderer": "iconify",
                # Previews are loaded by the browser from the Iconify API, so
                # the panel doesn't need any set to be downloaded.
                "sample_icons": [],
                "sample_names": info.get("samples", [])[:6],
            }
        return result

    async def prefixes(self, hass: HomeAssistant) -> list[str]:
        try:
            return list(await self.collections(hass))
        except Exception as err:
            LOGGER.debug("Iconify icon sets unavailable: %s", err)
            return []

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
