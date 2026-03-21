"""Sensor platform for Lumagen integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import LumagenState
from .const import DOMAIN
from .coordinator import LumagenCoordinator
from .entity import LumagenEntity


@dataclass(frozen=True, kw_only=True)
class LumagenSensorEntityDescription(SensorEntityDescription):
    """Describes Lumagen sensor entity."""

    value_fn: Callable[[LumagenState], Any]


STATUS_SENSORS: tuple[LumagenSensorEntityDescription, ...] = (
    LumagenSensorEntityDescription(
        key="logical_input",
        translation_key="logical_input",
        icon="mdi:video-input-hdmi",
        value_fn=lambda data: data.logical_input,
    ),
    LumagenSensorEntityDescription(
        key="physical_input",
        translation_key="physical_input",
        icon="mdi:video-input-component",
        value_fn=lambda data: data.physical_input,
    ),
    LumagenSensorEntityDescription(
        key="input_configuration",
        translation_key="input_configuration",
        icon="mdi:cog",
        value_fn=lambda data: data.input_config_number,
    ),
    # Source
    LumagenSensorEntityDescription(
        key="source_vertical_resolution",
        translation_key="source_vertical_resolution",
        icon="mdi:video",
        value_fn=lambda data: data.source_vertical_resolution,
    ),
    LumagenSensorEntityDescription(
        key="source_vertical_rate",
        translation_key="source_vertical_rate",
        icon="mdi:timer-outline",
        value_fn=lambda data: data.source_vertical_rate,
    ),
    LumagenSensorEntityDescription(
        key="source_content_aspect",
        translation_key="source_content_aspect",
        icon="mdi:aspect-ratio",
        value_fn=lambda data: data.source_content_aspect,
    ),
    LumagenSensorEntityDescription(
        key="source_raster_aspect",
        translation_key="source_raster_aspect",
        icon="mdi:aspect-ratio",
        value_fn=lambda data: data.source_raster_aspect,
    ),
    LumagenSensorEntityDescription(
        key="source_dynamic_range",
        translation_key="source_dynamic_range",
        icon="mdi:brightness-7",
        value_fn=lambda data: data.source_dynamic_range,
    ),
    LumagenSensorEntityDescription(
        key="source_mode",
        translation_key="source_mode",
        icon="mdi:scan-helper",
        value_fn=lambda data: data.source_mode,
    ),
    LumagenSensorEntityDescription(
        key="input_video_status",
        translation_key="input_video_status",
        icon="mdi:video-check",
        value_fn=lambda data: data.input_video_status,
    ),
    LumagenSensorEntityDescription(
        key="source_3d_mode",
        translation_key="source_3d_mode",
        icon="mdi:video-3d",
        value_fn=lambda data: data.source_3d_mode,
    ),
    LumagenSensorEntityDescription(
        key="nls_active",
        translation_key="nls_active",
        icon="mdi:arrow-expand-horizontal",
        value_fn=lambda data: data.nls_active,
    ),
    LumagenSensorEntityDescription(
        key="detected_content_aspect",
        translation_key="detected_content_aspect",
        icon="mdi:aspect-ratio",
        value_fn=lambda data: data.detected_content_aspect,
    ),
    LumagenSensorEntityDescription(
        key="detected_raster_aspect",
        translation_key="detected_raster_aspect",
        icon="mdi:aspect-ratio",
        value_fn=lambda data: data.detected_raster_aspect,
    ),
    # Output
    LumagenSensorEntityDescription(
        key="output_vertical_resolution",
        translation_key="output_vertical_resolution",
        icon="mdi:monitor",
        value_fn=lambda data: data.output_vertical_resolution,
    ),
    LumagenSensorEntityDescription(
        key="output_vertical_rate",
        translation_key="output_vertical_rate",
        icon="mdi:timer-outline",
        value_fn=lambda data: data.output_vertical_rate,
    ),
    LumagenSensorEntityDescription(
        key="output_aspect",
        translation_key="output_aspect",
        icon="mdi:aspect-ratio",
        value_fn=lambda data: data.output_aspect,
    ),
    LumagenSensorEntityDescription(
        key="output_3d_mode",
        translation_key="output_3d_mode",
        icon="mdi:video-3d",
        value_fn=lambda data: data.output_3d_mode,
    ),
    LumagenSensorEntityDescription(
        key="outputs_on",
        translation_key="outputs_on",
        icon="mdi:video-output",
        value_fn=lambda data: (
            ", ".join(
                str(i + 1)
                for i in range(4)
                if data.outputs_on is not None and data.outputs_on & (1 << i)
            )
            or None
        ),
    ),
    LumagenSensorEntityDescription(
        key="output_mode",
        translation_key="output_mode",
        icon="mdi:scan-helper",
        value_fn=lambda data: data.output_mode,
    ),
    LumagenSensorEntityDescription(
        key="output_colorspace",
        translation_key="output_colorspace",
        icon="mdi:palette",
        value_fn=lambda data: data.output_colorspace,
    ),
    LumagenSensorEntityDescription(
        key="output_cms",
        translation_key="output_cms",
        icon="mdi:palette",
        value_fn=lambda data: data.output_cms,
    ),
    LumagenSensorEntityDescription(
        key="output_cms_label",
        translation_key="output_cms_label",
        icon="mdi:palette",
        value_fn=lambda data: data.cms_label,
    ),
    LumagenSensorEntityDescription(
        key="output_style",
        translation_key="output_style",
        icon="mdi:image-filter-hdr",
        value_fn=lambda data: data.output_style,
    ),
    LumagenSensorEntityDescription(
        key="output_style_label",
        translation_key="output_style_label",
        icon="mdi:image-filter-hdr",
        value_fn=lambda data: data.style_label,
    ),
    LumagenSensorEntityDescription(
        key="input_label",
        translation_key="input_label",
        icon="mdi:label-outline",
        value_fn=lambda data: data.input_label,
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
        LumagenSensorEntity(coordinator, desc) for desc in STATUS_SENSORS
    )


class LumagenSensorEntity(LumagenEntity, SensorEntity):
    """A Lumagen sensor entity."""

    entity_description: LumagenSensorEntityDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    def _update_attrs(self) -> None:
        super()._update_attrs()
        data = self.coordinator.data
        self._attr_native_value = self.entity_description.value_fn(data)
