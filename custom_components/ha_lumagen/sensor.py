"""Sensor platform for Lumagen integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import LumagenState
from .const import DOMAIN
from .coordinator import LumagenCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LumagenSensorEntityDescription(SensorEntityDescription):
    """Describes Lumagen sensor entity."""

    value_fn: Callable[[LumagenState], Any]


def _format_output_resolution(data: LumagenState) -> str | None:
    """Format output resolution as a human-readable string."""
    if not data.output_vertical_resolution:
        return None
    rate = data.output_vertical_rate or 0
    return f"{data.output_vertical_resolution}@{rate}Hz"


STATUS_SENSORS: tuple[LumagenSensorEntityDescription, ...] = (
    LumagenSensorEntityDescription(
        key="logical_input",
        name="Logical Input",
        icon="mdi:video-input-hdmi",
        value_fn=lambda data: data.logical_input,
    ),
    LumagenSensorEntityDescription(
        key="physical_input",
        name="Physical Input",
        icon="mdi:video-input-component",
        value_fn=lambda data: data.physical_input,
    ),
    LumagenSensorEntityDescription(
        key="output_resolution",
        name="Output Resolution",
        icon="mdi:monitor",
        value_fn=_format_output_resolution,
    ),
    LumagenSensorEntityDescription(
        key="source_aspect_ratio",
        name="Source Aspect Ratio",
        icon="mdi:aspect-ratio",
        value_fn=lambda data: data.source_content_aspect,
    ),
    LumagenSensorEntityDescription(
        key="source_dynamic_range",
        name="Source Dynamic Range",
        icon="mdi:brightness-7",
        value_fn=lambda data: data.source_dynamic_range,
    ),
    LumagenSensorEntityDescription(
        key="input_configuration",
        name="Input Configuration",
        icon="mdi:cog",
        value_fn=lambda data: data.input_config_number,
    ),
    LumagenSensorEntityDescription(
        key="output_cms",
        name="Output CMS",
        icon="mdi:palette",
        value_fn=lambda data: data.output_cms,
    ),
    LumagenSensorEntityDescription(
        key="output_style",
        name="Output Style",
        icon="mdi:image-filter-hdr",
        value_fn=lambda data: data.output_style,
    ),
)

DIAGNOSTIC_SENSORS: tuple[LumagenSensorEntityDescription, ...] = (
    LumagenSensorEntityDescription(
        key="model_name",
        name="Model Name",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.model_name,
    ),
    LumagenSensorEntityDescription(
        key="software_revision",
        name="Software Revision",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.software_revision,
    ),
    LumagenSensorEntityDescription(
        key="model_number",
        name="Model Number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.model_number,
    ),
    LumagenSensorEntityDescription(
        key="serial_number",
        name="Serial Number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.serial_number,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumagen sensors."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LumagenSensorEntity(coordinator, desc)
        for desc in (*STATUS_SENSORS, *DIAGNOSTIC_SENSORS)
    )


class LumagenSensorEntity(CoordinatorEntity[LumagenCoordinator], SensorEntity):
    """A Lumagen sensor entity."""

    entity_description: LumagenSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

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
        if self.entity_description.entity_category == EntityCategory.DIAGNOSTIC:
            return data.connected
        return data.connected and data.device_status == "Active"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
