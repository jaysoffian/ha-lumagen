"""Async TCP client for Lumagen Radiance Pro."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Aspect ratio numeric codes (I24 SSS/AAA fields) → display names
ASPECT_RATIO_NAMES: dict[int, str] = {
    133: "4:3",
    178: "16:9",
    185: "1.85",
    190: "1.90",
    200: "2.00",
    210: "2.10",
    220: "2.20",
    235: "2.35",
    240: "2.40",
    255: "2.55",
    276: "2.76",
}

# Display name → RS232 command byte for setting aspect
ASPECT_COMMANDS: dict[str, str] = {
    "4:3": "[",
    "Letterbox": "]",
    "16:9": "*",
    "1.85": "/",
    "1.90": "A",
    "2.00": "C",
    "2.20": "E",
    "2.35": "K",
    "2.40": "G",
    "NLS": "N",
}

# Remote command name → RS232 byte
REMOTE_COMMANDS: dict[str, str] = {
    "up": "^",
    "down": "v",
    "left": "<",
    "right": ">",
    "menu": "M",
    "ok": "k",
    "enter": "k",
    "exit": "X",
    "back": "X",
    "home": "!",
    "info": "U",
    "alt": "#",
    "clear": "!",
    **{str(i): str(i) for i in range(10)},
}

_DYNAMIC_RANGE = {"0": "SDR", "1": "HDR"}
_SOURCE_MODE = {"i": "Interlaced", "p": "Progressive", "-": None}
_OUTPUT_COLORSPACE = {
    "0": "BT.601",
    "1": "BT.709",
    "2": "BT.2020",
    "3": "BT.2100",
}

# Regex for normal responses: !<letter><2digits>,<fields>
_RESPONSE_RE = re.compile(r"!([A-Z]\d{2}),(.*)")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class LumagenState:
    """Flat device state, updated in place by response handlers."""

    # Connection
    connected: bool = False

    # Identity (S01: model, sw_rev, model#, serial#)
    model_name: str | None = None
    software_revision: str | None = None
    model_number: str | None = None
    serial_number: str | None = None

    # Power
    device_status: str | None = None  # "Active" / "Standby"

    # Input (from I00 and I24)
    logical_input: int | None = None
    input_memory: str | None = None  # A / B / C / D
    physical_input: int | None = None
    input_config_number: int | None = None

    # Source (from I24)
    source_content_aspect: str | None = None  # "4:3", "16:9", "2.40", …
    source_raster_aspect: str | None = None
    detected_content_aspect: str | None = None
    detected_raster_aspect: str | None = None
    source_dynamic_range: str | None = None  # "SDR" / "HDR"
    source_mode: str | None = None  # "Progressive" / "Interlaced"
    source_vertical_rate: int | None = None
    source_vertical_resolution: int | None = None
    nls_active: bool = False

    # Output (from I24)
    output_vertical_rate: int | None = None
    output_vertical_resolution: int | None = None
    output_cms: int | None = None
    output_style: int | None = None
    output_colorspace: str | None = None
    output_aspect: str | None = None

    # Labels (populated by get_labels)
    input_labels: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response handlers — each returns True if state changed
# ---------------------------------------------------------------------------


def _aspect_name(code: str) -> str | None:
    """Convert numeric aspect code ('240') to display name ('2.40')."""
    try:
        val = int(code)
    except ValueError:
        return None
    if name := ASPECT_RATIO_NAMES.get(val):
        return name
    if val > 0:
        return f"{val / 100:.2f}"
    return None


def _setattr_changed(state: LumagenState, attr: str, val: object) -> bool:
    """Set *attr* on *state* if it differs; return True when changed."""
    if getattr(state, attr) != val:
        setattr(state, attr, val)
        return True
    return False


def _handle_device_id(state: LumagenState, fields: list[str]) -> bool:
    """S01 — model, sw_revision, model_number, serial_number."""
    if len(fields) < 4:
        return False
    changed = False
    changed |= _setattr_changed(state, "model_name", fields[0])
    changed |= _setattr_changed(state, "software_revision", fields[1])
    changed |= _setattr_changed(state, "model_number", fields[2])
    changed |= _setattr_changed(state, "serial_number", fields[3])
    return changed


def _handle_power(state: LumagenState, fields: list[str]) -> bool:
    """S02 — 0 = standby, 1 = active."""
    if not fields:
        return False
    new = "Active" if fields[0] == "1" else "Standby"
    return _setattr_changed(state, "device_status", new)


def _handle_input_info(state: LumagenState, fields: list[str]) -> bool:
    """I00 — logical input, memory bank, physical input."""
    if len(fields) < 3:
        return False
    changed = False
    try:
        changed |= _setattr_changed(state, "logical_input", int(fields[0]))
    except ValueError:
        pass
    changed |= _setattr_changed(state, "input_memory", fields[1])
    try:
        changed |= _setattr_changed(state, "physical_input", int(fields[2]))
    except ValueError:
        pass
    return changed


def _handle_full_info(state: LumagenState, fields: list[str]) -> bool:
    """I21/I22/I23/I24 — full device info.

    Field indices (0-based after splitting on commas):
      0=M  1=RRR  2=VVVV  3=D  4=X  5=AAA  6=SSS  7=Y  8=T  9=WWWW
      10=C 11=B   12=PPP  13=QQQQ 14=ZZZ
      15=E 16=F   17=G    18=H          (v2+)
      19=II 20=KK                       (v3+)
      21=JJJ 22=LLL                     (v4)
    """
    if len(fields) < 15:
        return False
    changed = False

    # Source vertical rate (RRR)
    try:
        changed |= _setattr_changed(state, "source_vertical_rate", int(fields[1]))
    except ValueError:
        pass
    # Source vertical resolution (VVVV)
    try:
        changed |= _setattr_changed(state, "source_vertical_resolution", int(fields[2]))
    except ValueError:
        pass
    # Input config number (X)
    try:
        changed |= _setattr_changed(state, "input_config_number", int(fields[4]))
    except ValueError:
        pass
    # Source raster aspect (AAA)
    changed |= _setattr_changed(state, "source_raster_aspect", _aspect_name(fields[5]))
    # Source content aspect (SSS)
    changed |= _setattr_changed(state, "source_content_aspect", _aspect_name(fields[6]))
    # NLS (Y)
    changed |= _setattr_changed(state, "nls_active", fields[7] == "N")
    # Output CMS (C)
    try:
        changed |= _setattr_changed(state, "output_cms", int(fields[10]))
    except ValueError:
        pass
    # Output style (B)
    try:
        changed |= _setattr_changed(state, "output_style", int(fields[11]))
    except ValueError:
        pass
    # Output vertical rate (PPP)
    try:
        changed |= _setattr_changed(state, "output_vertical_rate", int(fields[12]))
    except ValueError:
        pass
    # Output vertical resolution (QQQQ)
    try:
        changed |= _setattr_changed(
            state, "output_vertical_resolution", int(fields[13])
        )
    except ValueError:
        pass
    # Output aspect (ZZZ)
    changed |= _setattr_changed(state, "output_aspect", _aspect_name(fields[14]))

    # v2+ fields
    if len(fields) > 15:
        changed |= _setattr_changed(
            state, "output_colorspace", _OUTPUT_COLORSPACE.get(fields[15])
        )
    if len(fields) > 16:
        changed |= _setattr_changed(
            state, "source_dynamic_range", _DYNAMIC_RANGE.get(fields[16])
        )
    if len(fields) > 17:
        changed |= _setattr_changed(state, "source_mode", _SOURCE_MODE.get(fields[17]))

    # v3+ fields — II (virtual/logical input), KK (physical input)
    if len(fields) > 19:
        try:
            changed |= _setattr_changed(state, "logical_input", int(fields[19]))
        except ValueError:
            pass
    if len(fields) > 20:
        try:
            changed |= _setattr_changed(state, "physical_input", int(fields[20]))
        except ValueError:
            pass

    # v4 fields — JJJ (detected raster aspect), LLL (detected content aspect)
    if len(fields) > 21:
        changed |= _setattr_changed(
            state, "detected_raster_aspect", _aspect_name(fields[21])
        )
    if len(fields) > 22:
        changed |= _setattr_changed(
            state, "detected_content_aspect", _aspect_name(fields[22])
        )

    return changed


RESPONSE_HANDLERS: dict[str, Callable[[LumagenState, list[str]], bool]] = {
    "S01": _handle_device_id,
    "S02": _handle_power,
    "I00": _handle_input_info,
    "I21": _handle_full_info,
    "I22": _handle_full_info,
    "I23": _handle_full_info,
    "I24": _handle_full_info,
}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LumagenClient:
    """Async TCP client for a Lumagen Radiance Pro."""

    def __init__(self) -> None:
        self.state = LumagenState()
        self._host: str = ""
        self._port: int = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._running = False
        self._on_state_changed: Callable[[], None] | None = None
        self._on_connection_changed: Callable[[bool], None] | None = None
        self._alive_event: asyncio.Event | None = None
        self._write_lock = asyncio.Lock()
        # Label query correlation
        self._pending_label_id: str | None = None
        self._label_event: asyncio.Event | None = None
        self._last_label_value: str | None = None

    # -- Connection lifecycle -----------------------------------------------

    async def connect(
        self,
        host: str,
        port: int,
        on_state_changed: Callable[[], None] | None = None,
        on_connection_changed: Callable[[bool], None] | None = None,
    ) -> None:
        """Connect to the Lumagen device and start background tasks."""
        self._host = host
        self._port = port
        self._on_state_changed = on_state_changed
        self._on_connection_changed = on_connection_changed
        await self._open_connection()

    async def disconnect(self) -> None:
        """Shut down cleanly."""
        self._running = False
        for task in (self._reconnect_task, self._keepalive_task, self._read_task):
            if task and not task.done():
                task.cancel()
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self.state.connected = False

    async def _open_connection(self) -> None:
        """Open TCP socket and spin up read + keepalive tasks."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=10.0,
            )
        except (TimeoutError, OSError) as err:
            _LOGGER.error("Failed to connect to %s:%s: %s", self._host, self._port, err)
            self.state.connected = False
            if self._on_connection_changed:
                self._on_connection_changed(False)
            return

        self._running = True
        self.state.connected = True
        self._read_task = asyncio.create_task(self._read_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        if self._on_connection_changed:
            self._on_connection_changed(True)

    async def _handle_disconnect(self) -> None:
        """Tear down current connection and start reconnect loop."""
        if not self._running:
            return

        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
        self._reader = None
        self._writer = None

        was_connected = self.state.connected
        self.state.connected = False
        self.state.device_status = None  # ensure power-on detected on reconnect

        if was_connected:
            if self._on_connection_changed:
                self._on_connection_changed(False)
            self._notify_state_changed()

        # Start reconnect
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Retry the TCP connection every 30 s until success or shutdown."""
        while self._running:
            await asyncio.sleep(30)
            if not self._running:
                return
            _LOGGER.info("Attempting reconnect to %s:%s", self._host, self._port)
            await self._open_connection()
            if self.state.connected:
                _LOGGER.info("Reconnected to %s:%s", self._host, self._port)
                await self.fetch_full_state()
                return

    # -- Read loop ----------------------------------------------------------

    async def _read_loop(self) -> None:
        """Read lines from the device and dispatch to handlers."""
        while self._running and self._reader:
            try:
                line = await self._reader.readline()
                if not line:  # EOF
                    break
                text = line.decode("ascii", errors="ignore").strip()
                if text:
                    self._process_line(text)
            except asyncio.CancelledError:
                return
            except (OSError, ConnectionError):
                break
            except Exception:
                _LOGGER.debug("Read loop error", exc_info=True)
                break

        if self._running:
            await self._handle_disconnect()

    def _process_line(self, line: str) -> None:
        """Parse a single line from the TCP stream."""
        # Special power messages
        if "Power-up complete" in line:
            if _setattr_changed(self.state, "device_status", "Active"):
                self._notify_state_changed()
            return
        if "POWER OFF" in line:
            if _setattr_changed(self.state, "device_status", "Standby"):
                self._notify_state_changed()
            return

        # Ignore echoed commands and display noise
        # (lines that have no '!' at all are pure echo / ZT / ZY noise)
        if "!" not in line:
            return

        # Label response: !S1,<label text>
        # Check before the general regex because S1 has only one digit.
        label_idx = line.find("!S1,")
        if label_idx != -1:
            self._handle_label_response(line, label_idx)
            return

        # Normal response: !<letter><2 digits>,<fields>
        match = _RESPONSE_RE.search(line)
        if not match:
            return

        name = match.group(1)
        fields = match.group(2).split(",")

        # Alive response — just signal the event, no state change
        if name == "S00":
            if self._alive_event:
                self._alive_event.set()
            return

        handler = RESPONSE_HANDLERS.get(name)
        if handler:
            try:
                if handler(self.state, fields):
                    self._notify_state_changed()
            except Exception:
                _LOGGER.debug("Error in handler for %s", name, exc_info=True)

    def _handle_label_response(self, line: str, idx: int) -> None:
        """Extract label text and correlate with the pending query."""
        label_text = line[idx + 4 :]  # everything after "!S1,"

        # Determine which label ID this is for
        label_id = self._pending_label_id
        if not label_id:
            # Try to extract from the echo portion before the '!'
            echo = line[:idx]
            id_match = re.search(r"S1(\w{2})", echo)
            if id_match:
                label_id = id_match.group(1)

        if label_id:
            self._last_label_value = label_text
        if self._label_event:
            self._label_event.set()

    # -- Keepalive ----------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        """Send ZQS00 every 30 s; reconnect on timeout."""
        while self._running:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            self._alive_event = asyncio.Event()
            try:
                await self.send_command("ZQS00")
                await asyncio.wait_for(self._alive_event.wait(), timeout=5.0)
            except TimeoutError:
                _LOGGER.warning("Keepalive timeout — reconnecting")
                await self._handle_disconnect()
                return
            except asyncio.CancelledError:
                return

    # -- Sending ------------------------------------------------------------

    async def send_command(self, cmd: str) -> None:
        """Send a command string as raw bytes (no framing)."""
        await self._send_raw(cmd)

    async def _send_raw(self, data: str) -> None:
        """Write raw ASCII bytes to the device."""
        if not self._writer:
            _LOGGER.warning("Cannot send — not connected")
            return
        async with self._write_lock:
            try:
                self._writer.write(data.encode("ascii"))
                await self._writer.drain()
            except (OSError, ConnectionError) as err:
                _LOGGER.error("Send error: %s", err)
                self._reconnect_task = asyncio.create_task(self._handle_disconnect())

    def _notify_state_changed(self) -> None:
        if self._on_state_changed:
            self._on_state_changed()

    # -- State queries ------------------------------------------------------

    async def fetch_full_state(self) -> None:
        """Query identity, power, input, and full info."""
        for cmd in ("ZQS01", "ZQS02", "ZQI00", "ZQI24"):
            await self.send_command(cmd)
            await asyncio.sleep(0.05)  # brief pause between queries

    async def get_labels(self) -> dict[str, str]:
        """Query all input labels (A0-D9). Returns ``{id: text}``."""
        labels: dict[str, str] = {}
        for bank in "ABCD":
            for i in range(10):
                label_id = f"{bank}{i}"
                self._pending_label_id = label_id
                self._label_event = asyncio.Event()
                self._last_label_value = None
                await self.send_command(f"ZQS1{label_id}")
                try:
                    await asyncio.wait_for(self._label_event.wait(), timeout=2.0)
                    if self._last_label_value is not None:
                        labels[label_id] = self._last_label_value
                except TimeoutError:
                    _LOGGER.debug("Timeout waiting for label %s", label_id)
        self._pending_label_id = None
        self.state.input_labels = labels
        self._notify_state_changed()
        return labels

    def get_source_list(self) -> list[str]:
        """Return ordered source labels for the current memory bank."""
        bank = self.state.input_memory or "A"
        return [
            self.state.input_labels.get(f"{bank}{i}", f"Input {i + 1}")
            for i in range(10)
        ]

    # -- Convenience commands -----------------------------------------------

    async def power_on(self) -> None:
        """Power on the device."""
        await self._send_raw("%")

    async def power_off(self) -> None:
        """Power off (standby)."""
        await self._send_raw("$")

    async def select_input(self, number: int) -> None:
        """Select logical input (1-based)."""
        if 1 <= number <= 9:
            await self._send_raw(f"i{number}")
        elif 10 <= number <= 18:
            await self._send_raw(f"i+{number - 10}")

    async def select_memory(self, bank: str) -> None:
        """Select memory bank (A / B / C / D)."""
        await self._send_raw(bank.lower())

    async def set_aspect(self, aspect: str) -> None:
        """Set source aspect ratio by display name."""
        cmd = ASPECT_COMMANDS.get(aspect)
        if cmd is None:
            _LOGGER.warning("Unknown aspect ratio: %s", aspect)
            return
        await self._send_raw(cmd)

    async def send_remote_command(self, command: str) -> None:
        """Send a named remote-control command."""
        cmd = REMOTE_COMMANDS.get(command.lower())
        if cmd is None:
            _LOGGER.warning("Unknown remote command: %s", command)
            return
        await self._send_raw(cmd)

    # -- OSD ----------------------------------------------------------------

    async def display_message(self, text: str, duration: int = 3) -> None:
        """Show an OSD message.

        *duration*: 0-8 for timed (seconds), 9 for persistent.
        *text*: up to 60 chars (two 30-char lines separated by ``\\n``).
        """
        duration = max(0, min(9, duration))
        await self._send_raw(f"ZT{duration}{text}\r")

    async def clear_message(self) -> None:
        """Clear any OSD message."""
        await self._send_raw("ZC")
