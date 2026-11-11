"""State of a loaded IconHub config entry."""

from collections import defaultdict
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import CONF_ENABLED_SETS, DOMAIN
from .iconset_base import IconSetCollection
from .iconset_fapro import FontawesomeSets
from .iconset_iconify import IconifySets
from .iconset_local import LocalSet
from .iconset_webfont import WebfontSets


@dataclass
class IconHubData:
    icon_dir: str
    local: LocalSet
    fontawesome: FontawesomeSets
    webfont: WebfontSets
    iconify: IconifySets
    # Rendered icons by set prefix and icon name
    icon_cache: defaultdict = field(default_factory=lambda: defaultdict(dict))
    # Loader URL added to the frontend, removed again on unload
    js_url: str | None = None

    @classmethod
    def create(cls, icon_dir: str) -> "IconHubData":
        return cls(
            icon_dir=icon_dir,
            local=LocalSet(icon_dir),
            fontawesome=FontawesomeSets(icon_dir),
            webfont=WebfontSets(icon_dir),
            iconify=IconifySets(icon_dir),
        )

    @property
    def collections(self) -> list[IconSetCollection]:
        return [self.local, self.fontawesome, self.webfont, self.iconify]

    def flush(self) -> None:
        for collection in self.collections:
            collection.flush()
        self.icon_cache.clear()


type IconHubConfigEntry = ConfigEntry[IconHubData]


def get_loaded_entry(hass: HomeAssistant) -> IconHubConfigEntry | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and getattr(
            entry, "runtime_data", None
        ):
            return entry
    return None


def enabled_sets(entry: ConfigEntry) -> list[str]:
    sets = entry.options.get(CONF_ENABLED_SETS)
    if sets is None:
        # Entries created by early IconHub builds stored {prefix: bool} in data
        sets = [k for k, v in entry.data.items() if v is True]
    return list(sets)
