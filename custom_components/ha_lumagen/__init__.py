"""The Lumagen integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .client import LumagenClient
from .const import DEFAULT_PORT, DOMAIN
from .coordinator import LumagenCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.REMOTE,
]


SERVICE_DISPLAY_MESSAGE = "display_message"
SERVICE_DISPLAY_VOLUME = "display_volume"
SERVICE_CLEAR_MESSAGE = "clear_message"

DISPLAY_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("duration", default=3): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=9)
        ),
        vol.Optional("block_char", default=False): cv.boolean,
    }
)

DISPLAY_VOLUME_SCHEMA = vol.Schema(
    {
        vol.Required("volume"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)


def _get_coordinator(hass: HomeAssistant) -> LumagenCoordinator:
    """Return the first (and usually only) coordinator."""
    coordinators: dict = hass.data.get(DOMAIN, {})
    if not coordinators:
        raise ValueError("No Lumagen devices configured")
    return next(iter(coordinators.values()))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up domain-level services."""

    async def handle_display_message(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        message = call.data["message"]
        duration = call.data["duration"]
        if call.data["block_char"]:
            # Prepend ZBX so 'X' renders as █
            await coordinator.client.send_command(f"ZBXZT{duration}{message:.60}\r")
        else:
            await coordinator.client.display_message(message, duration)

    async def handle_display_volume(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.client.display_volume(call.data["volume"])

    async def handle_clear_message(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.client.clear_message()

    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_MESSAGE, handle_display_message, DISPLAY_MESSAGE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_VOLUME, handle_display_volume, DISPLAY_VOLUME_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_MESSAGE, handle_clear_message)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lumagen from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    client = LumagenClient()
    coordinator = LumagenCoordinator(hass, entry, client)

    try:
        await client.connect(
            host,
            port,
            on_state_changed=coordinator.handle_state_changed,
            on_connection_changed=coordinator.handle_connection_changed,
        )

        if not await client.wait_for(lambda s: s.connected, timeout=5):
            raise ConfigEntryNotReady("Device not connected")

        # Load stored identity + labels, or fetch from device
        has_stored = await coordinator.async_load_stored_state()

        if not has_stored:
            # First-ever setup — fetch identity and save
            await client.fetch_identity()
            if not await client.wait_for(lambda s: s.model_name is not None, timeout=5):
                _LOGGER.warning("Identity query timed out")

        # Always query power (runtime)
        await client.fetch_power()
        if not await client.wait_for(lambda s: s.power is not None, timeout=5):
            _LOGGER.warning("Power query timed out")

        # Query config toggles (game mode, auto aspect) so switches
        # have a known state from the start, not just when stored.
        await client.send_command("ZQI53")
        await client.send_command("ZQI54")

        # If device is on, fetch runtime state
        if client.state.power == "on":
            await client.fetch_runtime_state()
            await client.wait_for(lambda s: s.logical_input is not None, timeout=5)

    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.error("Failed to connect to Lumagen at %s:%s: %s", host, port, err)
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    # Save identity if we just fetched it
    if client.state.model_name:
        await coordinator.async_save_stored_state()

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Fetch labels before setting up platforms so select entities have options
    if not has_stored:
        await coordinator.refresh_config()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Lumagen integration ready (%s:%s)", host, port)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: LumagenCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
