"""Constants for the Lumagen integration."""

from homeassistant.exceptions import HomeAssistantError

DOMAIN = "ha_lumagen"
DEFAULT_PORT = 4999

ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UNKNOWN = "unknown"


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect to the device."""
