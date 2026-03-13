"""Config flow for Lumagen integration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

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
        """Open TCP, send alive query, check for Ok response."""
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5.0
            )
            writer.write(b"ZQS00")
            await writer.drain()
            data = await asyncio.wait_for(reader.readline(), timeout=5.0)
            return b"S00" in data and b"Ok" in data
        except Exception:
            _LOGGER.debug("Connection test failed for %s:%s", host, port, exc_info=True)
            return False
        finally:
            if writer:
                with suppress(Exception):
                    writer.close()
                    await writer.wait_closed()
