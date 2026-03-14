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
    async_add_entities([LumagenRefreshLabelsButton(coordinator)])


class LumagenRefreshLabelsButton(LumagenEntity, ButtonEntity):
    """Button to refresh all Lumagen labels."""

    _attr_name = "Refresh labels"
    _attr_icon = "mdi:label-multiple"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_refresh_labels"

    async def async_press(self) -> None:
        """Fetch all labels from the device."""
        await self.coordinator.fetch_labels_with_backoff()
