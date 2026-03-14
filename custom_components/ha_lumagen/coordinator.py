"""Data coordinator for Lumagen integration."""

from __future__ import annotations

import asyncio
import copy
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import LumagenClient, LumagenState
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class LumagenCoordinator(DataUpdateCoordinator[LumagenState]):
    """Coordinator for Lumagen — pure event-driven, no polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: LumagenClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self.client = client
        self.entry = entry

    # -- Callbacks wired to LumagenClient -----------------------------------

    def handle_state_changed(self) -> None:
        """Called (sync) by the client whenever device state changes."""
        new_data = copy.copy(self.client.state)

        # Detect standby → active transition
        old_power = self.data.power if self.data else None
        if new_data.power == "on" and old_power != "on":
            _LOGGER.info("Device powered on — scheduling full refresh")
            self.hass.async_create_task(self._handle_power_on())

        self.async_set_updated_data(new_data)

    def handle_connection_changed(self, connected: bool) -> None:
        """Called (sync) by the client on connect / disconnect."""
        _LOGGER.info("Connection %s", "established" if connected else "lost")
        self.async_set_updated_data(copy.copy(self.client.state))

    # -- Internal -----------------------------------------------------------

    async def _handle_power_on(self) -> None:
        """After power-on, wait for the device to settle then refresh."""
        await asyncio.sleep(10)
        try:
            await self.client.fetch_full_state()
        except Exception:
            _LOGGER.exception("Error during power-on refresh")

    async def fetch_labels_with_backoff(self, max_attempts: int = 5) -> None:
        """Fetch labels, retrying with backoff until all resolve."""
        for attempt in range(max_attempts):
            failed = await self.client.get_labels()
            if failed == 0:
                return
            delay = 5 * (attempt + 1)
            _LOGGER.warning(
                "%d label(s) failed — retrying in %ds (attempt %d/%d)",
                failed,
                delay,
                attempt + 1,
                max_attempts,
            )
            await asyncio.sleep(delay)
        _LOGGER.error(
            "Some labels could not be fetched after %d attempts", max_attempts
        )

    async def _async_update_data(self) -> LumagenState:
        """Fallback for first refresh — returns current state snapshot."""
        return copy.copy(self.client.state)

    async def async_shutdown(self) -> None:
        """Disconnect the client."""
        _LOGGER.info("Shutting down Lumagen coordinator")
        await self.client.disconnect()
