"""Config flow for Lumagen integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .client import LumagenClient
from .const import DEFAULT_PORT, DOMAIN, ERROR_CANNOT_CONNECT

_LOGGER = logging.getLogger(__name__)

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

    @staticmethod
    async def _test_connection(host: str, port: int) -> bool:
        """Connect via LumagenClient and verify the device responds."""
        client = LumagenClient()
        try:
            await client.connect(host, port)
            if not await client.wait_for(lambda s: s.connected, timeout=5):
                _LOGGER.debug("Connection test: TCP connect failed")
                return False
            await client.fetch_identity()
            if not await client.wait_for(lambda s: s.model_name is not None, timeout=5):
                _LOGGER.debug("Connection test: identity query timed out")
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
