"""The Lumagen integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

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
