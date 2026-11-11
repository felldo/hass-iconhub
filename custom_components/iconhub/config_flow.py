from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_ENABLED_SETS, DEFAULT_ENABLED_SETS, DOMAIN, LEGACY_DOMAIN


class IconHubConfigFlow(ConfigFlow, domain=DOMAIN):

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        enabled = list(DEFAULT_ENABLED_SETS)

        # Coming from Custom Icons: take over the icon sets enabled there
        if legacy := self.hass.config_entries.async_entries(LEGACY_DOMAIN):
            enabled = [k for k, v in legacy[0].data.items() if v is True] or enabled

        return self.async_create_entry(
            title="IconHub",
            data={},
            options={CONF_ENABLED_SETS: enabled},
        )
