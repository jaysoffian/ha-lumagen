"""Async TCP client for Lumagen Radiance Pro."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from contextlib import suppress
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

# Display name → RS232 command for setting aspect
ASPECT_COMMANDS: dict[str, str] = {
    "4:3": "[",
    "Letterbox": "]",
    "16:9": "*",
    "1.85": "/",
    "1.90": "A",
    "2.00": "C",
    "2.10": "+j",
    "2.20": "E",
    "2.35": "K",
    "2.40": "G",
    "2.55": "+W",
    "2.76": "+N",
    "NLS": "N",
}

# I20 aspect code → display name
_I20_ASPECT_CODES: dict[str, str] = {
    "0": "4:3",
    "1": "Letterbox",
    "2": "16:9",
    "3": "1.85",
    "4": "2.35",
    "8": "1.85 ALT",
    "9": "2.40",
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

# Regex for label responses: !S1<category>,<label text>
# Category is A-D (input banks) or 1-3 (custom mode / CMS / style).
_LABEL_RE = re.compile(r"!S1([A-D123]),")


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
    power: str | None = None  # "on" / "off"

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

    # Config (from I53)
    game_mode: bool | None = None

    # Labels (populated by get_labels)
    input_labels: dict[str, str] = field(default_factory=dict)
    custom_mode_labels: dict[str, str] = field(default_factory=dict)
    cms_labels: dict[str, str] = field(default_factory=dict)
    style_labels: dict[str, str] = field(default_factory=dict)


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
    old = getattr(state, attr)
    if old != val:
        _LOGGER.debug("state: %s: %r -> %r", attr, old, val)
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
    new = "on" if fields[0] == "1" else "off"
    return _setattr_changed(state, "power", new)


def _handle_input_info(state: LumagenState, fields: list[str]) -> bool:
    """I00 — logical input, memory bank, physical input."""
    if len(fields) < 3:
        return False
    changed = False
    changed |= _setattr_changed(state, "logical_input", _safe_int(fields[0]))
    changed |= _setattr_changed(state, "input_memory", fields[1])
    changed |= _setattr_changed(state, "physical_input", _safe_int(fields[2]))
    return changed


def _safe_int(s: str) -> int | None:
    """Parse an int, returning None on failure."""
    with suppress(ValueError):
        return int(s)
    return None


def _handle_full_info(state: LumagenState, fields: list[str]) -> bool:
    """I21/I22/I23/I24 — full device info.

    Field indices (0-based after splitting on commas):
      0=M  1=RRR  2=VVVV  3=D  4=X  5=AAA  6=SSS  7=Y  8=T  9=WWWW
      10=C 11=B   12=PPP  13=QQQQ 14=ZZZ
      15=E 16=F   17=G    18=H          (v2+)
      19=II 20=KK                       (v3+)
      21=JJJ 22=LLL                     (v4)

    Fields are ordered by protocol version. We parse as many as are
    present; an IndexError means we've reached the end of what this
    firmware version provides.
    """
    changed = False

    # v1 fields (0-14)
    if len(fields) < 15:
        return changed
    changed |= _setattr_changed(state, "source_vertical_rate", _safe_int(fields[1]))
    changed |= _setattr_changed(
        state, "source_vertical_resolution", _safe_int(fields[2])
    )
    changed |= _setattr_changed(state, "input_config_number", _safe_int(fields[4]))
    changed |= _setattr_changed(state, "source_raster_aspect", _aspect_name(fields[5]))
    changed |= _setattr_changed(state, "source_content_aspect", _aspect_name(fields[6]))
    changed |= _setattr_changed(state, "nls_active", fields[7] == "N")
    changed |= _setattr_changed(state, "output_cms", _safe_int(fields[10]))
    changed |= _setattr_changed(state, "output_style", _safe_int(fields[11]))
    changed |= _setattr_changed(state, "output_vertical_rate", _safe_int(fields[12]))
    changed |= _setattr_changed(
        state, "output_vertical_resolution", _safe_int(fields[13])
    )
    changed |= _setattr_changed(state, "output_aspect", _aspect_name(fields[14]))

    # v2+ fields (15-18)
    if len(fields) < 18:
        return changed
    changed |= _setattr_changed(
        state, "output_colorspace", _OUTPUT_COLORSPACE.get(fields[15])
    )
    changed |= _setattr_changed(
        state, "source_dynamic_range", _DYNAMIC_RANGE.get(fields[16])
    )
    changed |= _setattr_changed(state, "source_mode", _SOURCE_MODE.get(fields[17]))

    # v3+ fields (19-20) — II (virtual/logical input), KK (physical input)
    if len(fields) < 21:
        return changed
    changed |= _setattr_changed(state, "logical_input", _safe_int(fields[19]))
    changed |= _setattr_changed(state, "physical_input", _safe_int(fields[20]))

    # v4 fields (21-22) — detected raster/content aspect
    if len(fields) < 23:
        return changed
    changed |= _setattr_changed(
        state, "detected_raster_aspect", _aspect_name(fields[21])
    )
    changed |= _setattr_changed(
        state, "detected_content_aspect", _aspect_name(fields[22])
    )

    return changed


def _handle_game_mode(state: LumagenState, fields: list[str]) -> bool:
    """I53 — game mode status."""
    if not fields:
        return False
    return _setattr_changed(state, "game_mode", fields[0] == "1")


def _handle_aspect_mode(state: LumagenState, fields: list[str]) -> bool:
    """I20 — input aspect and NLS status.

    Response: !I20,<code><nls> where code=0-9 and nls='N' or '-'.
    """
    if not fields:
        return False
    val = fields[0]
    changed = False
    # Last char is NLS flag
    if val.endswith("N"):
        changed |= _setattr_changed(state, "nls_active", True)
        val = val[:-1]
    elif val.endswith("-"):
        changed |= _setattr_changed(state, "nls_active", False)
        val = val[:-1]
    if name := _I20_ASPECT_CODES.get(val):
        changed |= _setattr_changed(state, "source_content_aspect", name)
    return changed


RESPONSE_HANDLERS: dict[str, Callable[[LumagenState, list[str]], bool]] = {
    "S01": _handle_device_id,
    "S02": _handle_power,
    "I00": _handle_input_info,
    "I20": _handle_aspect_mode,
    "I21": _handle_full_info,
    "I22": _handle_full_info,
    "I23": _handle_full_info,
    "I24": _handle_full_info,
    "I53": _handle_game_mode,
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
        self._disconnecting = False
        self._on_state_changed: Callable[[], None] | None = None
        self._on_connection_changed: Callable[[bool], None] | None = None
        self._last_recv: float = 0.0
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
            with suppress(Exception):
                self._writer.close()
                await self._writer.wait_closed()
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

        _LOGGER.info("Connected to %s:%s", self._host, self._port)
        self._running = True
        self.state.connected = True
        self._read_task = asyncio.create_task(self._read_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        if self._on_connection_changed:
            self._on_connection_changed(True)

    async def _handle_disconnect(self) -> None:
        """Tear down current connection and start reconnect loop."""
        if not self._running or self._disconnecting:
            return
        _LOGGER.info("Disconnected from %s:%s", self._host, self._port)
        self._disconnecting = True

        # Cancel any in-progress reconnect before starting a new one
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self._writer:
            with suppress(Exception):
                self._writer.close()
        self._reader = None
        self._writer = None

        was_connected = self.state.connected
        self.state.connected = False

        if was_connected:
            if self._on_connection_changed:
                self._on_connection_changed(False)
            self._notify_state_changed()

        # Start reconnect
        self._disconnecting = False
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Retry the TCP connection with exponential backoff (1s → 30s max)."""
        delay = 1.0
        while self._running:
            _LOGGER.info(
                "Attempting reconnect to %s:%s in %.0fs", self._host, self._port, delay
            )
            await asyncio.sleep(delay)
            if not self._running:
                return
            await self._open_connection()
            if self.state.connected:
                _LOGGER.info("Reconnected to %s:%s", self._host, self._port)
                await self.fetch_power()
                await asyncio.sleep(0.05)
                await self.fetch_runtime_state()
                return
            delay = min(delay * 2, 30.0)

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
                    self._last_recv = time.monotonic()
                    _LOGGER.debug("recv: %s", text)
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
            if _setattr_changed(self.state, "power", "on"):
                self._notify_state_changed()
            return
        if "POWER OFF" in line:
            if _setattr_changed(self.state, "power", "off"):
                self._notify_state_changed()
            return

        # Ignore echoed commands and display noise
        # (lines that have no '!' at all are pure echo / ZT / ZY noise)
        if "!" not in line:
            return

        # Label response: !S1<cat>,<label text>
        # Check before the general regex because the code is only 2 chars (S1).
        if label_match := _LABEL_RE.search(line):
            self._handle_label_response(line, label_match)
            return

        # Normal response: !<letter><2 digits>,<fields>
        match = _RESPONSE_RE.search(line)
        if not match:
            return

        name = match.group(1)
        fields = match.group(2).split(",")

        # S00 is a no-op alive response — no state to update
        if name == "S00":
            return

        handler = RESPONSE_HANDLERS.get(name)
        if handler:
            try:
                if handler(self.state, fields):
                    self._notify_state_changed()
            except Exception:
                _LOGGER.debug("Error in handler for %s", name, exc_info=True)

    def _handle_label_response(self, line: str, match: re.Match[str]) -> None:
        """Extract label text and correlate with the pending query."""
        label_text = line[match.end() :]  # everything after "!S1<cat>,"

        # Determine which label ID this is for
        label_id = self._pending_label_id
        if not label_id:
            # Try to extract the full XY from the echoed query before the '!'
            echo = line[: match.start()]
            if id_match := re.search(r"S1(\w{2})", echo):
                label_id = id_match.group(1)

        if label_id:
            self._last_label_value = label_text
        if self._label_event:
            self._label_event.set()

    # -- Keepalive ----------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        """Poll input state when the connection has been idle for 30 s."""
        interval = 30
        probe_timeout = 5
        while self._running:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            # If we received data recently, no probe needed
            idle = time.monotonic() - self._last_recv
            if idle < interval:
                continue
            # Connection has been idle — send a probe
            before = self._last_recv
            try:
                await self.send_command("ZQI00")
                await asyncio.sleep(probe_timeout)
            except asyncio.CancelledError:
                return
            if self._last_recv == before:
                _LOGGER.warning("Keepalive timeout — reconnecting")
                await self._handle_disconnect()
                return

    # -- Sending ------------------------------------------------------------

    async def send_command(self, cmd: str) -> None:
        """Send a raw ASCII command string to the device (no framing)."""
        if not self._writer:
            _LOGGER.warning("Cannot send — not connected")
            return
        async with self._write_lock:
            try:
                _LOGGER.debug("send: %s", cmd)
                self._writer.write(cmd.encode("ascii"))
                await self._writer.drain()
            except (OSError, ConnectionError) as err:
                _LOGGER.error("Send error: %s", err)
                self._reconnect_task = asyncio.create_task(self._handle_disconnect())

    def _notify_state_changed(self) -> None:
        if self._on_state_changed:
            self._on_state_changed()

    # -- State queries ------------------------------------------------------

    async def fetch_identity(self) -> None:
        """Query device identity (model, firmware, serial)."""
        await self.send_command("ZQS01")

    async def fetch_power(self) -> None:
        """Query power state."""
        await self.send_command("ZQS02")

    async def fetch_runtime_state(self) -> None:
        """Query current input, output config, and signal info."""
        for cmd in ("ZQI00", "ZQI24"):
            await self.send_command(cmd)
            await asyncio.sleep(0.05)

    async def fetch_full_state(self) -> None:
        """Query identity, power, input, output config, and full info."""
        await self.fetch_identity()
        await asyncio.sleep(0.05)
        await self.fetch_power()
        await asyncio.sleep(0.05)
        await self.fetch_runtime_state()

    async def get_labels(self) -> int:
        """Query all labels (inputs A0-D9, custom modes, CMS, styles).

        Populates the per-category state fields and returns the number of
        labels that failed to resolve (0 = complete success).
        """
        all_labels: dict[str, str] = {}
        expected = 0

        # Input labels: A0-D9 (reverse iteration works around firmware bug)
        for bank in "ABCD":
            for i in reversed(range(10)):
                expected += 1
                label_id = f"{bank}{i}"
                val = await self._query_label(label_id)
                if val is not None:
                    all_labels[label_id] = val

        # Custom mode (1), CMS (2), Style (3) labels: X0-X7
        for category in "123":
            for i in range(8):
                expected += 1
                label_id = f"{category}{i}"
                val = await self._query_label(label_id)
                if val is not None:
                    all_labels[label_id] = val

        self.state.input_labels = {
            k: v for k, v in all_labels.items() if k[0] in "ABCD"
        }
        self.state.custom_mode_labels = {
            k: v for k, v in all_labels.items() if k[0] == "1"
        }
        self.state.cms_labels = {k: v for k, v in all_labels.items() if k[0] == "2"}
        self.state.style_labels = {k: v for k, v in all_labels.items() if k[0] == "3"}

        self._notify_state_changed()
        return expected - len(all_labels)

    async def _query_label(self, label_id: str) -> str | None:
        """Query a single label by ID. Returns the text or None on timeout."""
        self._pending_label_id = label_id
        self._label_event = asyncio.Event()
        self._last_label_value = None
        await self.send_command(f"ZQS1{label_id}")
        try:
            await asyncio.wait_for(self._label_event.wait(), timeout=2.0)
            return self._last_label_value
        except TimeoutError:
            _LOGGER.debug("Timeout waiting for label %s", label_id)
            return None
        finally:
            self._pending_label_id = None

    def get_source_list(self) -> list[str]:
        """Return ordered source labels for the current memory bank.

        Labels are stored per memory bank at indices 0-9, where label
        index 0 = logical input 1, index 9 = logical input 10.
        """
        bank = self.state.input_memory or "A"
        return [
            f"{self.state.input_labels.get(f'{bank}{i}', 'Input')} ({i + 1})"
            for i in range(10)
        ]

    # -- Convenience commands -----------------------------------------------

    async def power_on(self) -> None:
        """Power on the device."""
        await self.send_command("%")

    async def power_off(self) -> None:
        """Power off (standby)."""
        await self.send_command("$")

    async def select_input(self, number: int) -> None:
        """Select a logical input by number (1-19).

        Physical HDMI port count varies by model (1-10), but logical
        (virtual) inputs can go up to 19.  RS232 protocol: ``i1``-``i9``
        for inputs 1-9, ``i+0``-``i+9`` for inputs 10-19.
        """
        if 1 <= number <= 9:
            await self.send_command(f"i{number}")
        elif 10 <= number <= 19:
            await self.send_command(f"i+{number - 10}")
        await self.send_command("ZQI00")

    async def select_memory(self, bank: str) -> None:
        """Select memory bank (A / B / C / D)."""
        await self.send_command(bank.lower())
        await asyncio.sleep(0.5)
        await self.send_command("ZQI00")

    async def set_aspect(self, aspect: str) -> None:
        """Set source aspect ratio by display name."""
        cmd = ASPECT_COMMANDS.get(aspect)
        if cmd is None:
            _LOGGER.warning("Unknown aspect ratio: %s", aspect)
            return
        await self.send_command(cmd)

    async def send_remote_command(self, command: str) -> None:
        """Send a named remote-control command."""
        cmd = REMOTE_COMMANDS.get(command.lower())
        if cmd is None:
            _LOGGER.warning("Unknown remote command: %s", command)
            return
        await self.send_command(cmd)

    # -- OSD ----------------------------------------------------------------

    async def display_message(self, text: str, duration: int = 3) -> None:
        """Show an OSD message.

        *duration*: 0-8 for timed (seconds), 9 for persistent.
        *text*: up to 60 chars (two 30-char lines separated by ``\\n``).
        """
        duration = max(0, min(9, duration))
        await self.send_command(f"ZT{duration}{text}\r")

    async def clear_message(self) -> None:
        """Clear any OSD message."""
        await self.send_command("ZC")

    # -- Output config ------------------------------------------------------

    async def set_output_config(
        self,
        mode: int | None = None,
        cms: int | None = None,
        style: int | None = None,
    ) -> None:
        """Set output mode/CMS/style (0-7 each, None to keep current).

        Uses ZY530MCS where each position is 0-7 or K (keep).
        """
        m = str(mode) if mode is not None else "K"
        c = str(cms) if cms is not None else "K"
        s = str(style) if style is not None else "K"
        await self.send_command(f"ZY530{m}{c}{s}\r")
        await self.send_command("ZQI24")

    async def set_game_mode(self, enabled: bool) -> None:
        """Enable or disable game mode."""
        await self.send_command(f"ZY551{'1' if enabled else '0'}\r")
        await self.send_command("ZQI53")

    async def set_auto_aspect(self, enabled: bool) -> None:
        """Enable or disable auto aspect detection."""
        await self.send_command("~" if enabled else "V")

    # -- Labels -------------------------------------------------------------

    async def set_label(self, category: str, index: int, text: str) -> None:
        """Set a label on the device.

        *category*: 'A'-'D' (input per memory bank), '0' (all input banks),
                    '1' (custom mode), '2' (CMS), '3' (style).
        *index*: label index (0-9 for inputs, 0-7 for modes/CMS/styles).
        *text*: label text.
        """
        await self.send_command(f"ZY524{category}{index}{text}\r")
        # Re-fetch to confirm
        await self._query_label(f"{category}{index}")

    # -- Misc ---------------------------------------------------------------

    async def save_config(self) -> None:
        """Save current configuration to flash."""
        await self.send_command("ZY6SAVECONFIG\r")

    async def trigger_hotplug(self, input_num: int | None = None) -> None:
        """Toggle HDMI hotplug on an input (or all inputs if None)."""
        target = str(input_num) if input_num is not None else "A"
        await self.send_command(f"ZY520{target}\r")
