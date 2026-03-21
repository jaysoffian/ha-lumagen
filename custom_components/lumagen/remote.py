"""Remote platform for Lumagen integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import REMOTE_COMMANDS
from .const import DOMAIN
from .coordinator import LumagenCoordinator
from .entity import LumagenEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumagen remote."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LumagenRemoteEntity(coordinator)])


class LumagenRemoteEntity(LumagenEntity, RemoteEntity):
    """Remote entity for Lumagen menu navigation."""

    _attr_translation_key = "remote"
    _attr_icon = "mdi:remote"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_remote"

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        if data is None:
            return
        # Available in standby so power-on works via the remote entity
        self._attr_available = self.coordinator.last_update_success and data.connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_off()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        data = self.coordinator.data
        if not data or not data.power:
            _LOGGER.warning("Cannot send commands while device is in standby")
            return

        for cmd in command:
            if cmd.lower() in REMOTE_COMMANDS:
                await self.coordinator.client.send_remote_command(cmd)
                await asyncio.sleep(0.1)
            else:
                _LOGGER.warning("Unknown remote command: %s (ignored)", cmd)
