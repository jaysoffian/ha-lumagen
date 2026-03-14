"""Button platform for Lumagen integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up Lumagen buttons."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LumagenRefreshConfigButton(coordinator),
            LumagenResetAutoAspectButton(coordinator),
        ]
    )


class LumagenRefreshConfigButton(LumagenEntity, ButtonEntity):
    """Button to refresh identity and labels from the device."""

    _attr_name = "Refresh config"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_refresh_labels"

    @property
    def available(self) -> bool:
        """Available whenever connected, regardless of power state."""
        return self.coordinator.last_update_success and self.coordinator.data.connected

    async def async_press(self) -> None:
        """Fetch identity and labels from the device."""
        await self.coordinator.refresh_config()


class LumagenResetAutoAspectButton(LumagenEntity, ButtonEntity):
    """Button to reset auto aspect detection."""

    _attr_name = "Reset auto aspect"
    _attr_icon = "mdi:aspect-ratio"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_reset_auto_aspect"

    async def async_press(self) -> None:
        """Reset auto aspect detection on the device."""
        await self.coordinator.client.send_command("ZY550\r")
