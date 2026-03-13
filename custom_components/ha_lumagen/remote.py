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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import REMOTE_COMMANDS
from .const import DOMAIN
from .coordinator import LumagenCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumagen remote."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LumagenRemoteEntity(coordinator)])


class LumagenRemoteEntity(CoordinatorEntity[LumagenCoordinator], RemoteEntity):
    """Remote entity for Lumagen menu navigation."""

    _attr_has_entity_name = True
    _attr_name = "Remote"
    _attr_icon = "mdi:remote"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_remote"

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry.entry_id)},
            "name": f"Lumagen {data.model_name or 'RadiancePro'}",
            "manufacturer": "Lumagen",
            "model": data.model_name or "RadiancePro",
            "sw_version": data.software_revision,
            "serial_number": data.serial_number,
        }

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            self.coordinator.last_update_success
            and data.connected
            and data.device_status == "Active"
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_off()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        if self.coordinator.data.device_status != "Active":
            _LOGGER.warning("Cannot send commands while device is in standby")
            return

        for cmd in command:
            if cmd.lower() in REMOTE_COMMANDS:
                await self.coordinator.client.send_remote_command(cmd)
                await asyncio.sleep(0.1)
            else:
                _LOGGER.warning("Unknown remote command: %s (ignored)", cmd)
