"""Constants for the Lumagen integration."""

from homeassistant.exceptions import HomeAssistantError

DOMAIN = "ha_lumagen"
DEFAULT_PORT = 4999

ERROR_CANNOT_CONNECT = "cannot_connect"

CONF_ASPECT_RATIOS = "aspect_ratios"


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect to the device."""
