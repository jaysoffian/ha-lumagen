"""Number platform for Lumagen integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up Lumagen number entities."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LumagenFanSpeedNumber(coordinator)])


class LumagenFanSpeedNumber(LumagenEntity, NumberEntity):
    """Lumagen minimum fan speed (1-10).

    The device has no query command for this setting, so we track
    it optimistically and assume the factory default (1) at startup.
    """

    _attr_name = "Minimum Fan Speed"
    _attr_icon = "mdi:fan"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = 1

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_fan_speed"

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        if data is None:
            return
        # Config entity — available whenever connected (even in standby)
        self._attr_available = self.coordinator.last_update_success and data.connected

    async def async_set_native_value(self, value: float) -> None:
        """Set the fan speed."""
        await self.coordinator.client.set_min_fan_speed(int(value))
        self._attr_native_value = value
        self.async_write_ha_state()
