"""Button platform for Lumagen integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up Lumagen buttons."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LumagenReloadConfigButton(coordinator),
            LumagenRestartOutputsButton(coordinator),
            LumagenNlsButton(coordinator),
        ]
    )


class LumagenReloadConfigButton(LumagenEntity, ButtonEntity):
    """Button to reload identity, config, and labels from the device."""

    _attr_translation_key = "reload_config"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_reload_config"

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        # Available whenever connected (even in standby)
        self._attr_available = self.coordinator.last_update_success and data.connected

    async def async_press(self) -> None:
        """Reload identity, config, and labels from the device."""
        await self.coordinator.reload_config()


class LumagenRestartOutputsButton(LumagenEntity, ButtonEntity):
    """Restart outputs if TV/projector has trouble locking on the signal."""

    _attr_translation_key = "restart_outputs"
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_restart_outputs"

    async def async_press(self) -> None:
        """Restart outputs via ALT, PREV remote sequence."""
        await self.coordinator.client.restart_outputs()


class LumagenNlsButton(LumagenEntity, ButtonEntity):
    """Send the NLS command to the Lumagen."""

    _attr_translation_key = "nls"
    _attr_icon = "mdi:stretch-to-page-outline"

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_nls"

    async def async_press(self) -> None:
        """Send the NLS command and poll for updated state."""
        await self.coordinator.client.send_nls_command()
