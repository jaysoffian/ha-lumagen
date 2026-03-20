"""Data coordinator for Lumagen integration."""

from __future__ import annotations

import copy
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import LumagenClient, LumagenState
from .const import DOMAIN

STORAGE_VERSION = 1

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
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.info"
        )

    # -- Callbacks wired to LumagenClient -----------------------------------

    def on_state_changed(self) -> None:
        """Called (sync) by the client whenever device state changes."""
        self.async_set_updated_data(copy.deepcopy(self.client.state))

    def on_connection_changed(self, connected: bool) -> None:
        """Called (sync) by the client on connect / disconnect."""
        _LOGGER.info("Connection %s", "established" if connected else "lost")
        self.async_set_updated_data(copy.deepcopy(self.client.state))

    # -- Internal -----------------------------------------------------------

    async def async_load_stored_state(self) -> bool:
        """Load identity, config, and labels from disk into client state.

        Returns True if found.
        """
        data = await self._store.async_load()
        if not data:
            return False
        self.client.state.load_stored_dict(data)
        self.async_set_updated_data(copy.deepcopy(self.client.state))
        _LOGGER.debug("Loaded identity and labels from storage")
        return True

    async def async_save_stored_state(self) -> None:
        """Persist identity, config, and labels to disk."""
        await self._store.async_save(self.client.state.to_stored_dict())

    async def reload_config(self) -> None:
        """Re-fetch identity, config state, and labels from device."""
        await self.client.reload_config()
        await self.async_save_stored_state()

    async def _async_update_data(self) -> LumagenState:
        """Fallback for first refresh — returns current state snapshot."""
        return copy.deepcopy(self.client.state)

    async def async_shutdown(self) -> None:
        """Disconnect the client."""
        _LOGGER.info("Shutting down Lumagen coordinator")
        await self.client.disconnect()
