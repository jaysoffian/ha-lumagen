"""Config flow for Lumagen integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .client import ASPECT_COMMANDS, LumagenClient
from .const import CONF_ASPECT_RATIOS, DEFAULT_PORT, DOMAIN, ERROR_CANNOT_CONNECT

_LOGGER = logging.getLogger(__name__)

ALL_ASPECT_KEYS = list(ASPECT_COMMANDS.keys())

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)


class LumagenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lumagen."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return LumagenOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user configuration — host and port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            if await self._test_connection(host, port):
                await self.async_set_unique_id(f"{host}_{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Lumagen ({host})",
                    data=user_input,
                )
            errors["base"] = ERROR_CANNOT_CONNECT

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of host and port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            if await self._test_connection(host, port):
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    title=f"Lumagen ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                    unique_id=f"{host}_{port}",
                )
            errors["base"] = ERROR_CANNOT_CONNECT

        entry = self._get_reconfigure_entry()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str,
                    vol.Required(
                        CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    async def _test_connection(host: str, port: int) -> bool:
        """Connect via LumagenClient and verify the device responds."""
        client = LumagenClient()
        try:
            await client.connect(host, port)
            if not await client.wait_for(lambda s: s.connected, timeout=5):
                _LOGGER.debug("Connection test: TCP connect failed")
                return False
            await client.query_runtime()
            if not await client.wait_for(lambda s: s.power is not None, timeout=5):
                _LOGGER.debug("Connection test: device did not respond")
                return False
            return True
        except Exception:
            _LOGGER.debug(
                "Connection test failed for %s:%s",
                host,
                port,
                exc_info=True,
            )
            return False
        finally:
            await client.disconnect()


class LumagenOptionsFlow(OptionsFlow):
    """Handle Lumagen options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure which aspect ratios appear in the select menu."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(CONF_ASPECT_RATIOS, ALL_ASPECT_KEYS)

        schema = vol.Schema(
            {
                vol.Required(CONF_ASPECT_RATIOS, default=current): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=k, label=k) for k in ALL_ASPECT_KEYS
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
