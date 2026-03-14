"""The Lumagen integration."""

from __future__ import annotations

import asyncio
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
        # Give initial queries time to complete
        await asyncio.sleep(3)

        if not client.state.connected:
            raise ConfigEntryNotReady("Device not connected")

        # Load stored identity + labels, or fetch from device
        has_stored = await coordinator.async_load_stored_state()

        if not has_stored:
            # First-ever setup — fetch identity and save
            await client.fetch_identity()
            await asyncio.sleep(1)

        # Always query power (runtime)
        await client.fetch_power()
        await asyncio.sleep(1)

        # If device is on, fetch runtime state
        if client.state.power == "on":
            await client.fetch_runtime_state()
            await asyncio.sleep(1)

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Fetch identity + labels from device if none stored
    if not has_stored:
        hass.async_create_task(coordinator.refresh_config())

    _LOGGER.info("Lumagen integration ready (%s:%s)", host, port)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: LumagenCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
