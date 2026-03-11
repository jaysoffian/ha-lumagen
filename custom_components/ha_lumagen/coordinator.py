"""Data coordinator for Lumagen integration."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from lumagen import DeviceInfo
from lumagen.constants import ConnectionStatus, DeviceStatus, EventType
from lumagen.device_manager import DeviceManager

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class LumagenData:
    """Data structure for Lumagen device state."""

    device_info: DeviceInfo
    is_connected: bool
    is_alive: bool
    device_status: DeviceStatus


class LumagenCoordinator(DataUpdateCoordinator[LumagenData]):
    """Coordinator for Lumagen device with pure event-driven updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_manager: DeviceManager,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # Pure event-driven — no polling
        )
        self.device_manager = device_manager
        self.entry = entry
        self._event_listeners: list[tuple] = []
        self._setup_event_listeners()

    def _setup_event_listeners(self) -> None:
        """Subscribe to pylumagen dispatcher events.

        pylumagen emits two event types: DATA_RECEIVED (for all parsed
        device messages) and CONNECTION_STATE.  We listen for both and
        pull the current state from DeviceManager on every event.
        """
        dispatcher = self.device_manager.dispatcher

        data_handler = lambda et, ed: asyncio.create_task(
            self._handle_data_received(et, ed)
        )
        dispatcher.register_listener(EventType.DATA_RECEIVED, data_handler)
        self._event_listeners.append((EventType.DATA_RECEIVED, data_handler))

        conn_handler = lambda et, ed: asyncio.create_task(
            self._handle_connection_state(et, ed)
        )
        dispatcher.register_listener(EventType.CONNECTION_STATE, conn_handler)
        self._event_listeners.append((EventType.CONNECTION_STATE, conn_handler))

        _LOGGER.debug("Event listeners registered for DATA_RECEIVED and CONNECTION_STATE")

    def _snapshot(self, **overrides) -> LumagenData:
        """Build a LumagenData snapshot from current DeviceManager state."""
        return LumagenData(
            device_info=overrides.get("device_info", self.device_manager.device_info),
            is_connected=overrides.get("is_connected", self.device_manager.is_connected),
            is_alive=overrides.get("is_alive", self.device_manager.is_alive),
            device_status=overrides.get("device_status", self.device_manager.device_status),
        )

    async def _handle_data_received(self, _event_type, _event_data: dict) -> None:
        """Handle any parsed message from the device."""
        new_data = self._snapshot()

        # Skip update if nothing changed (e.g. echoed commands from other clients)
        if self.data == new_data:
            return

        # Detect power-on transition and schedule a full state refresh
        old_status = self.data.device_status if self.data else None
        if (
            old_status == DeviceStatus.STANDBY
            and new_data.device_status == DeviceStatus.ACTIVE
        ):
            _LOGGER.info("Device powered on, scheduling full refresh in 5 seconds")
            asyncio.create_task(self._delayed_refresh_on_power_on())

        self.async_set_updated_data(new_data)

    async def _delayed_refresh_on_power_on(self) -> None:
        """Refresh all device state shortly after power on."""
        await asyncio.sleep(5)
        try:
            _LOGGER.debug("Executing full refresh after power on")
            await self.device_manager.executor.get_all()
        except Exception as err:
            _LOGGER.error("Failed to refresh after power on: %s", err)

    async def _handle_connection_state(self, _event_type, event_data: dict) -> None:
        """Handle connection state changes."""
        state = event_data.get("state")
        _LOGGER.info("Connection state changed: %s", state)

        if state == ConnectionStatus.CONNECTED:
            await asyncio.sleep(1)
            try:
                await self.device_manager.executor.get_labels()
                _LOGGER.debug("Labels fetched after connection")
            except Exception as err:
                _LOGGER.error("Error fetching labels: %s", err, exc_info=True)

        self.async_set_updated_data(self._snapshot())

    async def _async_update_data(self) -> LumagenData:
        """Return current state (unused — update_interval is None)."""
        return self._snapshot()

    def _cleanup_event_listeners(self) -> None:
        """Unregister all event listeners."""
        if not self.device_manager or not hasattr(self.device_manager, "dispatcher"):
            return

        dispatcher = self.device_manager.dispatcher
        remove = getattr(dispatcher, "remove_listener", None) or getattr(
            dispatcher, "unregister_listener", None
        )
        if not remove:
            _LOGGER.debug("Dispatcher has no remove/unregister method, skipping cleanup")
            return

        for event_type, handler in self._event_listeners:
            try:
                remove(event_type, handler)
            except Exception as err:
                _LOGGER.debug("Error removing listener for %s: %s", event_type, err)

        self._event_listeners.clear()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close device connection."""
        _LOGGER.info("Shutting down Lumagen coordinator")
        self._cleanup_event_listeners()

        if self.device_manager:
            try:
                await self.device_manager.close()
                _LOGGER.info("Device connection closed")
            except Exception as err:
                _LOGGER.error("Error closing device connection: %s", err, exc_info=True)
