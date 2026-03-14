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
        self._pending_i24_task: asyncio.Task | None = None

    # -- Callbacks wired to LumagenClient -----------------------------------

    def handle_state_changed(self) -> None:
        """Called (sync) by the client whenever device state changes."""
        new_data = copy.copy(self.client.state)

        old_power = self.data.power if self.data else None
        old_input = self.data.logical_input if self.data else None

        # Detect standby → active transition (not initial state discovery)
        if new_data.power == "on" and old_power == "off":
            _LOGGER.info("Device powered on — scheduling runtime state refresh")
            self.hass.async_create_task(self._handle_power_on())

        # Detect input change — fetch memory bank and (if needed) signal info
        if (
            new_data.logical_input is not None
            and new_data.logical_input != old_input
            and old_input is not None
        ):
            self.hass.async_create_task(self.client.send_command("ZQI00"))
            self._schedule_i24_if_needed()

        self.async_set_updated_data(new_data)

    def handle_connection_changed(self, connected: bool) -> None:
        """Called (sync) by the client on connect / disconnect."""
        _LOGGER.info("Connection %s", "established" if connected else "lost")
        self.async_set_updated_data(copy.copy(self.client.state))

    # -- Internal -----------------------------------------------------------

    def _schedule_i24_if_needed(self) -> None:
        """Schedule a ZQI24 query, skipping it if an unsolicited one arrives first."""
        if self._pending_i24_task and not self._pending_i24_task.done():
            self._pending_i24_task.cancel()
        self._pending_i24_task = self.hass.async_create_task(self._fetch_i24_if_stale())

    async def _fetch_i24_if_stale(self) -> None:
        """Wait briefly, then send ZQI24 only if none arrived in the meantime."""
        before = self.client.last_i24_time
        await asyncio.sleep(1)
        if self.client.last_i24_time == before:
            await self.client.send_command("ZQI24")

    async def _handle_power_on(self) -> None:
        """After power-on, wait for the device to settle then refresh."""
        await asyncio.sleep(10)
        try:
            await self.client.fetch_runtime_state()
        except Exception:
            _LOGGER.exception("Error during runtime state refresh")

    async def async_load_stored_state(self) -> bool:
        """Load identity + labels from disk into client state. Returns True if found."""
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
        # Labels
        s.input_labels = data.get("input_labels", {})
        s.custom_mode_labels = data.get("custom_mode_labels", {})
        s.cms_labels = data.get("cms_labels", {})
        s.style_labels = data.get("style_labels", {})
        self.async_set_updated_data(copy.copy(s))
        _LOGGER.debug("Loaded identity and labels from storage")
        return True

    async def async_save_stored_state(self) -> None:
        """Persist identity + labels to disk."""
        s = self.client.state
        await self._store.async_save(
            {
                "model_name": s.model_name,
                "software_revision": s.software_revision,
                "model_number": s.model_number,
                "serial_number": s.serial_number,
                "game_mode": s.game_mode,
                "input_labels": s.input_labels,
                "custom_mode_labels": s.custom_mode_labels,
                "cms_labels": s.cms_labels,
                "style_labels": s.style_labels,
            }
        )

    async def refresh_config(self, max_attempts: int = 5) -> None:
        """Fetch identity, game mode, and labels from device."""
        await self.client.fetch_identity()
        await asyncio.sleep(0.05)
        await self.client.send_command("ZQI53")
        await asyncio.sleep(1)
        for attempt in range(max_attempts):
            failed = await self.client.get_labels()
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
        return copy.copy(self.client.state)

    async def async_shutdown(self) -> None:
        """Disconnect the client."""
        _LOGGER.info("Shutting down Lumagen coordinator")
        await self.client.disconnect()
