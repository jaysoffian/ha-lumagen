"""Switch platform for Lumagen integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LumagenCoordinator
from .entity import LumagenEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumagen power switch."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LumagenPowerSwitch(coordinator)])


class LumagenPowerSwitch(LumagenEntity, SwitchEntity):
    """Lumagen power switch."""

    _attr_name = "Power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_power"
        self._optimistic_state: bool | None = None

    @property
    def available(self) -> bool:
        """Power switch is available whenever connected (even in standby)."""
        return self.coordinator.last_update_success and self.coordinator.data.connected

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        return self.coordinator.data.power == "on"

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_on()
        self._optimistic_state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_off()
        self._optimistic_state = False
        self.async_write_ha_state()
