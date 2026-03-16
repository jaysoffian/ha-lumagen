"""Base entity for the Lumagen integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LumagenCoordinator


class LumagenEntity(CoordinatorEntity[LumagenCoordinator]):
    """Base class for Lumagen entities — shared device_info and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)

    def _update_attrs(self) -> None:
        """Recompute _attr_ values from coordinator data. Override in subclasses."""
        data = self.coordinator.data
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.entry.entry_id)},
            "name": f"Lumagen {data.model_name or 'RadiancePro'}",
            "manufacturer": "Lumagen",
            "model": data.model_name or "RadiancePro",
            "sw_version": data.software_revision,
            "serial_number": data.serial_number,
        }
        self._attr_available = (
            self.coordinator.last_update_success
            and data.connected
            and data.power == "on"
        )

    def _handle_coordinator_update(self) -> None:
        self._update_attrs()
        super()._handle_coordinator_update()
