"""Base entity for the Lumagen integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LumagenCoordinator


class LumagenEntity(CoordinatorEntity[LumagenCoordinator]):
    """Base class for Lumagen entities — shared device_info and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator)

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
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data
        return data.connected and data.device_status == "Active"
