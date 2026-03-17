"""Switch platform for Lumagen integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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
    """Set up Lumagen switches."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LumagenPowerSwitch(coordinator),
            LumagenAutoAspectSwitch(coordinator),
            LumagenGameModeSwitch(coordinator),
        ]
    )


class LumagenPowerSwitch(LumagenEntity, SwitchEntity):
    """Lumagen power switch."""

    _attr_name = "Power"
    _attr_icon = "mdi:power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_power"
        self._optimistic_state: bool | None = None

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        if data is None:
            return
        # Available whenever connected (even in standby, so user can turn on)
        self._attr_available = self.coordinator.last_update_success and data.connected
        if self._optimistic_state is not None:
            self._attr_is_on = self._optimistic_state
        else:
            self._attr_is_on = data.power == "on"

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_on()
        self._optimistic_state = True
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_off()
        self._optimistic_state = False
        self._attr_is_on = False
        self.async_write_ha_state()


class LumagenAutoAspectSwitch(LumagenEntity, SwitchEntity):
    """Lumagen auto aspect switch."""

    _attr_name = "Auto Aspect"
    _attr_icon = "mdi:aspect-ratio"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_auto_aspect"
        self._optimistic_state: bool | None = None

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        if data is None:
            return
        if self._optimistic_state is not None:
            self._attr_is_on = self._optimistic_state
        else:
            self._attr_is_on = data.auto_aspect

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_auto_aspect(True)
        self._optimistic_state = True
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_auto_aspect(False)
        self._optimistic_state = False
        self._attr_is_on = False
        self.async_write_ha_state()


class LumagenGameModeSwitch(LumagenEntity, SwitchEntity):
    """Lumagen game mode switch."""

    _attr_name = "Game Mode"
    _attr_icon = "mdi:gamepad-variant"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_game_mode"
        self._optimistic_state: bool | None = None

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        if data is None:
            return
        if self._optimistic_state is not None:
            self._attr_is_on = self._optimistic_state
        else:
            self._attr_is_on = data.game_mode

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_game_mode(True)
        self._optimistic_state = True
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_game_mode(False)
        self._optimistic_state = False
        self._attr_is_on = False
        self.async_write_ha_state()
