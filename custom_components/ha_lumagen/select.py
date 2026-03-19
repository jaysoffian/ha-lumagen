"""Select platform for Lumagen integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import ASPECT_COMMANDS, InputMemory, LumagenState
from .const import DOMAIN
from .coordinator import LumagenCoordinator
from .entity import LumagenEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LumagenSelectEntityDescription(SelectEntityDescription):
    """Describes Lumagen select entity."""

    current_option_fn: Callable[[LumagenState, LumagenCoordinator], str | None]
    select_option_fn: Callable[[LumagenCoordinator, str], Any]
    options_fn: Callable[[LumagenCoordinator], list[str]] | None = None
    static_options: list[str] | None = None


# -- Option callbacks -------------------------------------------------------


def _current_input_source(data: LumagenState, coord: LumagenCoordinator) -> str | None:
    """Map logical_input back to its label in the current source list."""
    if data.logical_input is None:
        return None
    source_list = coord.client.get_source_list()
    idx = data.logical_input - 1  # logical_input is 1-based
    if 0 <= idx < len(source_list):
        return source_list[idx]
    return None


async def _select_input_source(coord: LumagenCoordinator, option: str) -> None:
    source_list = coord.client.get_source_list()
    try:
        input_number = source_list.index(option) + 1  # 1-based
    except ValueError:
        _LOGGER.error("Could not find input number for label: %s", option)
        return
    await coord.client.select_input(input_number)


def _current_aspect(data: LumagenState, _coord: LumagenCoordinator) -> str | None:
    if data.source_raster_aspect == "1.33" and data.source_content_aspect == "1.78":
        return "Letterbox"
    return data.source_content_aspect


async def _select_aspect(coord: LumagenCoordinator, option: str) -> None:
    await coord.client.set_aspect(option)


def _current_memory(data: LumagenState, _coord: LumagenCoordinator) -> str | None:
    if data.input_memory is None:
        return None
    return f"MEM{data.input_memory}"


async def _select_memory(coord: LumagenCoordinator, option: str) -> None:
    await coord.client.select_memory(cast("InputMemory", option[-1]))  # "MEMA" → "A"


# -- Entity descriptions ----------------------------------------------------

SELECT_ENTITIES: tuple[LumagenSelectEntityDescription, ...] = (
    LumagenSelectEntityDescription(
        key="input",
        name="Input",
        icon="mdi:video-input-hdmi",
        current_option_fn=_current_input_source,
        select_option_fn=_select_input_source,
        options_fn=lambda coord: coord.client.get_source_list(),
    ),
    LumagenSelectEntityDescription(
        key="aspect_ratio",
        name="Aspect Ratio",
        icon="mdi:aspect-ratio",
        current_option_fn=_current_aspect,
        select_option_fn=_select_aspect,
        static_options=list(ASPECT_COMMANDS.keys()),
    ),
    LumagenSelectEntityDescription(
        key="memory",
        name="Memory",
        icon="mdi:memory",
        current_option_fn=_current_memory,
        select_option_fn=_select_memory,
        static_options=["MEMA", "MEMB", "MEMC", "MEMD"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumagen select entities."""
    coordinator: LumagenCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LumagenSelectEntity(coordinator, desc) for desc in SELECT_ENTITIES
    )


class LumagenSelectEntity(LumagenEntity, SelectEntity):
    """A Lumagen select entity."""

    entity_description: LumagenSelectEntityDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSelectEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._optimistic_option: str | None = None
        # HA reads options during entity registration, before the first
        # coordinator update calls _update_attrs, so seed them here.
        if description.static_options:
            self._attr_options = description.static_options
        elif description.options_fn:
            self._attr_options = description.options_fn(coordinator)
        else:
            self._attr_options = []

    def _update_attrs(self) -> None:
        super()._update_attrs()
        if self.coordinator.data is None:
            return
        if self.entity_description.static_options:
            self._attr_options = self.entity_description.static_options
        elif self.entity_description.options_fn:
            self._attr_options = self.entity_description.options_fn(self.coordinator)
        else:
            self._attr_options = []
        if self._optimistic_option is not None:
            self._attr_current_option = self._optimistic_option
        else:
            self._attr_current_option = self.entity_description.current_option_fn(
                self.coordinator.data, self.coordinator
            )

    def _handle_coordinator_update(self) -> None:
        self._optimistic_option = None
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        self._optimistic_option = option
        self._attr_current_option = option
        self.async_write_ha_state()
        try:
            await self.entity_description.select_option_fn(self.coordinator, option)
        except Exception:
            self._optimistic_option = None
            self._update_attrs()
            self.async_write_ha_state()
            raise
