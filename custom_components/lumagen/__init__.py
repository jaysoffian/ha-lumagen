"""The Lumagen integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import LumagenCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.REMOTE,
]


SERVICE_SHOW_OSD_MESSAGE = "show_osd_message"
SERVICE_SHOW_OSD_VOLUME_BAR = "show_osd_volume_bar"
SERVICE_CLEAR_OSD_MESSAGE = "clear_osd_message"

SHOW_OSD_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("line_one"): cv.string,
        vol.Optional("line_two", default=""): cv.string,
        vol.Optional("duration", default=3): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=8)
        ),
        vol.Optional("block_char", default=""): cv.string,
    },
    extra=vol.REMOVE_EXTRA,
)

SHOW_OSD_VOLUME_BAR_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("level"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
        vol.Optional("label", default=None): vol.Any(None, cv.string),
    },
    extra=vol.REMOVE_EXTRA,
)

CLEAR_OSD_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
    },
    extra=vol.REMOVE_EXTRA,
)


def _get_coordinator(hass: HomeAssistant, entity_id: str) -> LumagenCoordinator:
    """Resolve an entity_id to its LumagenCoordinator."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry is None or entry.config_entry_id is None:
        raise ServiceValidationError(f"Unknown entity: {entity_id}")

    coordinators: dict[str, LumagenCoordinator] = hass.data.get(DOMAIN, {})
    coordinator = coordinators.get(entry.config_entry_id)
    if coordinator is None:
        raise ServiceValidationError(f"No Lumagen coordinator for entity: {entity_id}")

    return coordinator


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up domain-level services."""

    async def show_osd_message(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["entity_id"])
        await coordinator.client.show_osd_message(
            line_one=call.data["line_one"],
            line_two=call.data["line_two"],
            duration=call.data["duration"],
            block_char=call.data["block_char"],
        )

    async def show_osd_volume_bar(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["entity_id"])
        await coordinator.client.show_osd_volume_bar(
            call.data["level"], label=call.data.get("label")
        )

    async def clear_osd_message(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["entity_id"])
        await coordinator.client.clear_osd_message()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOW_OSD_MESSAGE,
        show_osd_message,
        SHOW_OSD_MESSAGE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOW_OSD_VOLUME_BAR,
        show_osd_volume_bar,
        SHOW_OSD_VOLUME_BAR_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_OSD_MESSAGE,
        clear_osd_message,
        CLEAR_OSD_MESSAGE_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lumagen from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    coordinator = LumagenCoordinator(hass, entry, host, port)

    try:
        await coordinator.async_connect()

        if not await coordinator.client.wait_for(lambda s: s.connected, timeout=5):
            raise ConfigEntryNotReady("Device not connected")

        # Seed device info from stored state (identity + labels)
        has_stored = await coordinator.async_load_stored_state()

        if not has_stored and not await coordinator.client.query_config():
            raise ConfigEntryNotReady("Config query incomplete")

        # Kick off runtime state (power arrives shortly after)
        await coordinator.client.query_runtime()

    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.error("Failed to set up Lumagen at %s:%s: %s", host, port, err)
        raise ConfigEntryNotReady(f"Failed to set up: {err}") from err

    if not has_stored:
        await coordinator.async_save_stored_state()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info("Lumagen integration ready (%s:%s)", host, port)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: LumagenCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
