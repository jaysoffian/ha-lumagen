"""Select platform for Lumagen integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import ASPECT_COMMANDS, LumagenState
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
    if data.nls_active:
        return "NLS"
    return data.source_content_aspect


async def _select_aspect(coord: LumagenCoordinator, option: str) -> None:
    await coord.client.set_aspect(option)


def _current_memory(data: LumagenState, _coord: LumagenCoordinator) -> str | None:
    return data.input_memory


async def _select_memory(coord: LumagenCoordinator, option: str) -> None:
    await coord.client.select_memory(option)


# -- Entity descriptions ----------------------------------------------------

SELECT_ENTITIES: tuple[LumagenSelectEntityDescription, ...] = (
    LumagenSelectEntityDescription(
        key="input_source",
        name="Input Source",
        icon="mdi:video-input-hdmi",
        current_option_fn=_current_input_source,
        select_option_fn=_select_input_source,
        options_fn=lambda coord: coord.client.get_source_list(),
    ),
    LumagenSelectEntityDescription(
        key="source_aspect_ratio",
        name="Source Aspect Ratio",
        icon="mdi:aspect-ratio",
        current_option_fn=_current_aspect,
        select_option_fn=_select_aspect,
        static_options=list(ASPECT_COMMANDS.keys()),
    ),
    LumagenSelectEntityDescription(
        key="memory_bank",
        name="Memory Bank",
        icon="mdi:memory",
        current_option_fn=_current_memory,
        select_option_fn=_select_memory,
        static_options=["A", "B", "C", "D"],
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

    @property
    def options(self) -> list[str]:
        if self.entity_description.static_options:
            return self.entity_description.static_options
        if self.entity_description.options_fn:
            return self.entity_description.options_fn(self.coordinator)
        return []

    @property
    def current_option(self) -> str | None:
        return self.entity_description.current_option_fn(
            self.coordinator.data, self.coordinator
        )

    async def async_select_option(self, option: str) -> None:
        await self.entity_description.select_option_fn(self.coordinator, option)
