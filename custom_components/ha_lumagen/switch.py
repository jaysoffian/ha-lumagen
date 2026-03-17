"""Switch platform for Lumagen integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import LumagenState
from .const import DOMAIN
from .coordinator import LumagenCoordinator
from .entity import LumagenEntity


@dataclass(frozen=True, kw_only=True)
class LumagenSwitchEntityDescription:
    """Describes a Lumagen switch entity."""

    key: str
    name: str
    icon: str
    is_on_fn: Callable[[LumagenState], bool | None]
    turn_on_fn: Callable[[LumagenCoordinator], Awaitable[None]]
    turn_off_fn: Callable[[LumagenCoordinator], Awaitable[None]]
    entity_category: EntityCategory | None = None
    available_in_standby: bool = False


SWITCH_ENTITIES: tuple[LumagenSwitchEntityDescription, ...] = (
    LumagenSwitchEntityDescription(
        key="power",
        name="Power",
        icon="mdi:power",
        is_on_fn=lambda s: s.power == "on",
        turn_on_fn=lambda c: c.client.power_on(),
        turn_off_fn=lambda c: c.client.power_off(),
        available_in_standby=True,
    ),
    LumagenSwitchEntityDescription(
        key="auto_aspect",
        name="Auto Aspect",
        icon="mdi:aspect-ratio",
        is_on_fn=lambda s: s.auto_aspect,
        turn_on_fn=lambda c: c.client.set_auto_aspect(True),
        turn_off_fn=lambda c: c.client.set_auto_aspect(False),
    ),
    LumagenSwitchEntityDescription(
        key="game_mode",
        name="Game Mode",
        icon="mdi:gamepad-variant",
        is_on_fn=lambda s: s.game_mode,
        turn_on_fn=lambda c: c.client.set_game_mode(True),
        turn_off_fn=lambda c: c.client.set_game_mode(False),
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumagen switches."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LumagenSwitchEntity(coordinator, desc) for desc in SWITCH_ENTITIES
    )


class LumagenSwitchEntity(LumagenEntity, SwitchEntity):
    """A Lumagen switch entity with optimistic state."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    entity_description: LumagenSwitchEntityDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        if description.entity_category:
            self._attr_entity_category = description.entity_category
        self._optimistic_state: bool | None = None

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        if data is None:
            return
        if self.entity_description.available_in_standby:
            self._attr_available = (
                self.coordinator.last_update_success and data.connected
            )
        if self._optimistic_state is not None:
            self._attr_is_on = self._optimistic_state
        else:
            self._attr_is_on = self.entity_description.is_on_fn(data)

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.entity_description.turn_on_fn(self.coordinator)
        self._optimistic_state = True
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.entity_description.turn_off_fn(self.coordinator)
        self._optimistic_state = False
        self._attr_is_on = False
        self.async_write_ha_state()
