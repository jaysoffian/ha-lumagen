"""Data coordinator for Lumagen integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import cast

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
        host: str,
        port: int,
        delimeters: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self.client = LumagenClient(host, port, delimeters)
        self.entry = entry
        self._store: Store[dict[str, object]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.info"
        )

    async def async_connect(self) -> None:
        """Connect to the Lumagen device."""
        await self.client.connect(
            on_state_changed=self.on_state_changed,
            on_connection_changed=self.on_connection_changed,
        )

    # -- Callbacks wired to LumagenClient -----------------------------------

    def on_state_changed(self) -> None:
        """Called (sync) by the client whenever device state changes."""
        self.async_set_updated_data(self.client.state)

    def on_connection_changed(self, connected: bool) -> None:
        """Called (sync) by the client on connect / disconnect."""
        _LOGGER.info("Connection %s", "established" if connected else "lost")
        self.async_set_updated_data(self.client.state)

    # -- Internal -----------------------------------------------------------

    async def async_load_stored_state(self) -> bool:
        """Load identity, config, and labels from disk into client state.

        Returns True if found.
        """
        data = await self._store.async_load()
        if not data:
            return False
        self.client.state.load_stored_dict(data)
        self.async_set_updated_data(self.client.state)
        _LOGGER.debug("Loaded identity and labels from storage")
        return True

    async def async_save_stored_state(self) -> None:
        """Persist identity, config, and labels to disk."""
        data = self.client.state.to_stored_dict()
        # data["labels"] = dict(data["labels"]) # Copy to ensure updates are saved
        # Copy to ensure updates are saved
        data["labels"] = dict(cast(Iterable[list[bytes]], data["labels"]))
        await self._store.async_save(data)

    async def reload_config(self) -> None:
        """Re-fetch identity and labels from device."""
        if not await self.client.query_config():
            _LOGGER.warning("Config reload incomplete — stored state not updated")
            return
        await self.async_save_stored_state()
        _LOGGER.info("Config reloaded from device")

    async def _async_update_data(self) -> LumagenState:
        """Fallback for first refresh — returns current state snapshot."""
        return self.client.state

    async def async_shutdown(self) -> None:
        """Disconnect the client."""
        _LOGGER.info("Shutting down Lumagen coordinator")
        await self.client.disconnect()
