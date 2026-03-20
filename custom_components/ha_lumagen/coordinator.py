"""Data coordinator for Lumagen integration."""

from __future__ import annotations

import asyncio
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
        s = self.client.state
        # Identity
        s.model_name = data.get("model_name")
        s.software_revision = data.get("software_revision")
        s.model_number = data.get("model_number")
        s.serial_number = data.get("serial_number")
        # Config
        if "game_mode" in data:
            s.game_mode = data["game_mode"]
        if "auto_aspect" in data:
            s.auto_aspect = data["auto_aspect"]
        # Labels
        s.labels.update(data.get("labels", {}))
        self.async_set_updated_data(copy.deepcopy(s))
        _LOGGER.debug("Loaded identity and labels from storage")
        return True

    async def async_save_stored_state(self) -> None:
        """Persist identity, config, and labels to disk."""
        s = self.client.state
        await self._store.async_save(
            {
                "model_name": s.model_name,
                "software_revision": s.software_revision,
                "model_number": s.model_number,
                "serial_number": s.serial_number,
                "game_mode": s.game_mode,
                "auto_aspect": s.auto_aspect,
                "labels": dict(s.labels),
            }
        )

    async def reload_config(self, max_attempts: int = 5) -> None:
        """Re-fetch identity, config state, and labels from device."""
        for attempt in range(max_attempts):
            failed = await self.client.reload_config()
            if failed == 0:
                await self.async_save_stored_state()
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
        return copy.deepcopy(self.client.state)

    async def async_shutdown(self) -> None:
        """Disconnect the client."""
        _LOGGER.info("Shutting down Lumagen coordinator")
        await self.client.disconnect()
