"""Async TCP client for Lumagen Radiance Pro."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Literal, cast

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

PowerState = Literal["on", "off"]
InputMemory = Literal["A", "B", "C", "D", "a", "b", "c", "d"]
DynamicRange = Literal["SDR", "HDR"]
SourceMode = Literal["Progressive", "Interlaced"]
OutputMode = Literal["Progressive", "Interlaced"]
InputVideoStatus = Literal["No Source", "Active Video", "Test Pattern"]
OutputColorspace = Literal["BT.601", "BT.709", "BT.2020", "BT.2100"]
ThreeDMode = Literal[
    "Off", "Frame Sequential", "Frame Packed", "Top-Bottom", "Side-by-Side"
]
LabelCategory = Literal["A", "B", "C", "D", "0", "1", "2", "3"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Aspect ratio numeric codes (I24 SSS/AAA fields) → display names
ASPECT_RATIO_NAMES: dict[int, str] = {
    133: "1.33",
    178: "1.78",
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

# Display name → RS232 command(s) for setting aspect.
# NLS requires a base aspect first (e.g. 1.33 then N), so the NLS
# entries are two-command sequences.
ASPECT_COMMANDS: dict[str, list[str]] = {
    "Auto": ["~"],
    "1.33": ["["],
    "Letterbox": ["]"],
    "1.78": ["*"],
    "1.85": ["/"],
    "1.90": ["A"],
    "2.00": ["C"],
    "2.10": ["+j"],
    "2.20": ["E"],
    "2.35": ["K"],
    "2.40": ["G"],
    "2.55": ["+W"],
    "2.76": ["+N"],
    "1.33 NLS": ["[", "N"],
    "1.78 NLS": ["*", "N"],
    "1.85 NLS": ["/", "N"],
}

# I20 aspect code → display name
_I20_ASPECT_CODES: dict[str, str] = {
    "0": "1.33",
    "1": "Letterbox",
    "2": "1.78",
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
    "previous": "P",
    "pip_off": "e",
    "pip_select": "p",
    "pip_swap": "r",
    "pip_mode": "m",
    "save": "S",
    "hdr_setup": "Y",
    "test_pattern": "H",
    "osd_on": "g",
    "osd_off": "s",
    **{str(i): str(i) for i in range(10)},
}

_DYNAMIC_RANGE: dict[str, DynamicRange] = {"0": "SDR", "1": "HDR"}
_SOURCE_MODE: dict[str, SourceMode | None] = {
    "i": "Interlaced",
    "p": "Progressive",
    "-": None,
}
_OUTPUT_MODE: dict[str, OutputMode] = {"I": "Interlaced", "P": "Progressive"}
_OUTPUT_COLORSPACE: dict[str, OutputColorspace] = {
    "0": "BT.601",
    "1": "BT.709",
    "2": "BT.2020",
    "3": "BT.2100",
}
_INPUT_VIDEO_STATUS: dict[str, InputVideoStatus] = {
    "0": "No Source",
    "1": "Active Video",
    "2": "Test Pattern",
}
_3D_MODE: dict[str, ThreeDMode] = {
    "0": "Off",
    "1": "Frame Sequential",
    "2": "Frame Packed",
    "4": "Top-Bottom",
    "8": "Side-by-Side",
}

# Regex for normal responses: !<letter><2digits>,<fields>
_RESPONSE_RE = re.compile(r"!([A-Z]\d{2}),(.*)")

# Regex for label responses: !S1<category>,<label text>
# Category is A-D (input memories) or 1-3 (custom mode / CMS / style).
_LABEL_RE = re.compile(r"!S1([A-D123]),")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class LumagenState:
    """Flat device state, updated in place by response handlers.

    Tracks field-level changes via ``__setattr__``.  Any assignment that
    actually modifies a value appends the field name to ``_changed`` and
    emits a debug log line.  Callers should call ``clear_changed()``
    before a batch of updates and inspect ``_changed`` (truthy if any
    field was modified) afterward to decide whether to notify listeners.
    """

    # Connection
    connected: bool = False

    # Identity (S01: model, sw_rev, model#, serial#)
    model_name: str | None = None
    software_revision: str | None = None
    model_number: str | None = None
    serial_number: str | None = None

    # Power
    power: PowerState | None = None

    # Input (from I00 and I24)
    logical_input: int | None = None
    input_memory: InputMemory | None = None
    physical_input: int | None = None
    input_config_number: int | None = None

    # Video status (from I2x field 0)
    input_video_status: InputVideoStatus | None = None

    # Source (from I24)
    source_content_aspect: str | None = None  # "1.33", "1.78", "2.40", …
    source_raster_aspect: str | None = None
    detected_content_aspect: str | None = None
    detected_raster_aspect: str | None = None
    source_dynamic_range: DynamicRange | None = None
    source_mode: SourceMode | None = None
    source_3d_mode: ThreeDMode | None = None
    source_vertical_rate: int | None = None
    source_vertical_resolution: int | None = None
    nls_active: bool = False

    # Output (from I24)
    output_vertical_rate: int | None = None
    output_vertical_resolution: int | None = None
    output_cms: int | None = None
    output_style: int | None = None
    output_colorspace: OutputColorspace | None = None
    output_aspect: str | None = None
    output_3d_mode: ThreeDMode | None = None
    output_mode: OutputMode | None = None
    outputs_on: int | None = None  # raw bitmask from WWWW field

    # Config (from I53, I54)
    game_mode: bool | None = None
    auto_aspect: bool | None = None

    # Labels (populated by get_labels)
    input_labels: dict[str, str] = field(default_factory=dict)
    custom_mode_labels: dict[str, str] = field(default_factory=dict)
    cms_labels: dict[str, str] = field(default_factory=dict)
    style_labels: dict[str, str] = field(default_factory=dict)

    # Change tracking (not part of equality/repr)
    _changed: list[str] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    def __setattr__(self, name: str, value: object) -> None:
        try:
            old = object.__getattribute__(self, name)
        except AttributeError:
            pass  # Initial assignment during __init__
        else:
            if old != value and name != "_changed":
                _LOGGER.debug("state: %s: %r -> %r", name, old, value)
                # _changed may not exist yet during __init__ when a
                # keyword arg overrides a field that was already set
                # to its default value by the dataclass-generated code.
                changed = self.__dict__.get("_changed")
                if changed is not None:
                    changed.append(name)
        object.__setattr__(self, name, value)

    def clear_changed(self) -> None:
        """Reset the change-tracking list."""
        object.__getattribute__(self, "_changed").clear()


# ---------------------------------------------------------------------------
# Response handlers — mutate state directly; changes tracked by __setattr__
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


def _handle_device_id(state: LumagenState, fields: list[str]) -> None:
    """S01 — model, sw_revision, model_number, serial_number."""
    if len(fields) < 4:
        return
    state.model_name = fields[0]
    state.software_revision = fields[1]
    state.model_number = fields[2]
    state.serial_number = fields[3]


def _handle_power(state: LumagenState, fields: list[str]) -> None:
    """S02 — 0 = standby, 1 = active."""
    if not fields:
        return
    state.power = "on" if fields[0] == "1" else "off"


def _handle_input_info(state: LumagenState, fields: list[str]) -> None:
    """I00 — logical input, input memory, physical input."""
    if len(fields) < 3:
        return
    state.logical_input = _safe_int(fields[0])
    state.input_memory = cast("InputMemory", fields[1])
    state.physical_input = _safe_int(fields[2])


def _safe_int(s: str) -> int | None:
    """Parse an int, returning None on failure."""
    with suppress(ValueError):
        return int(s)
    return None


def _parse_outputs_on(hex_str: str) -> int | None:
    """Parse WWWW hex bitmask into an integer."""
    try:
        return int(hex_str, 16)
    except ValueError:
        return None


def _handle_full_info(state: LumagenState, fields: list[str]) -> None:
    """I21/I22/I23/I24/I25 — full device info.

    Field indices (0-based after splitting on commas):
      0=M  1=RRR  2=VVVV  3=D  4=X  5=AAA  6=SSS  7=Y  8=T  9=WWWW
      10=C 11=B   12=PPP  13=QQQQ 14=ZZZ
      15=E 16=F   17=G    18=H          (v2+)
      19=II 20=KK                       (v3+)
      21=JJJ 22=LLL                     (v4+)
      23=MEM 24=PWR                       (v5)

    Fields are ordered by protocol version. We parse as many as are
    present; an IndexError means we've reached the end of what this
    firmware version provides.
    """
    # v1 fields (0-14)
    if len(fields) < 15:
        return
    state.input_video_status = _INPUT_VIDEO_STATUS.get(fields[0])
    state.source_vertical_rate = _safe_int(fields[1])
    state.source_vertical_resolution = _safe_int(fields[2])
    state.source_3d_mode = _3D_MODE.get(fields[3])
    state.input_config_number = _safe_int(fields[4])
    state.source_raster_aspect = _aspect_name(fields[5])
    state.source_content_aspect = _aspect_name(fields[6])
    state.nls_active = fields[7] == "N"
    state.output_3d_mode = _3D_MODE.get(fields[8])
    state.outputs_on = _parse_outputs_on(fields[9])
    state.output_cms = _safe_int(fields[10])
    state.output_style = _safe_int(fields[11])
    state.output_vertical_rate = _safe_int(fields[12])
    state.output_vertical_resolution = _safe_int(fields[13])
    state.output_aspect = _aspect_name(fields[14])

    # v2+ fields (15-18)
    if len(fields) < 19:
        return
    state.output_colorspace = _OUTPUT_COLORSPACE.get(fields[15])
    state.source_dynamic_range = _DYNAMIC_RANGE.get(fields[16])
    state.source_mode = _SOURCE_MODE.get(fields[17])
    state.output_mode = _OUTPUT_MODE.get(fields[18])

    # v3+ fields (19-20) — II (virtual/logical input), KK (physical input)
    if len(fields) < 21:
        return
    state.logical_input = _safe_int(fields[19])
    state.physical_input = _safe_int(fields[20])

    # v4 fields (21-22) — detected raster/content aspect
    if len(fields) < 23:
        return
    state.detected_raster_aspect = _aspect_name(fields[21])
    state.detected_content_aspect = _aspect_name(fields[22])

    # v5 fields (23-24) — input memory, power status
    if len(fields) < 25:
        return
    mem = fields[23]
    if mem in ("A", "B", "C", "D"):
        state.input_memory = cast("InputMemory", mem)
    state.power = "on" if fields[24] == "1" else "off"


def _handle_game_mode(state: LumagenState, fields: list[str]) -> None:
    """I53 — game mode status."""
    if not fields:
        return
    state.game_mode = fields[0] == "1"


def _handle_auto_aspect(state: LumagenState, fields: list[str]) -> None:
    """I54 — auto aspect status (fw ≥041824)."""
    if not fields:
        return
    state.auto_aspect = fields[0] == "1"


def _handle_aspect_mode(state: LumagenState, fields: list[str]) -> None:
    """I20 — input aspect and NLS status.

    Response: !I20,<code><nls> where code=0-9 and nls='N' or '-'.
    """
    if not fields:
        return
    val = fields[0]
    # Last char is NLS flag
    if val.endswith("N"):
        state.nls_active = True
        val = val[:-1]
    elif val.endswith("-"):
        state.nls_active = False
        val = val[:-1]
    if name := _I20_ASPECT_CODES.get(val):
        state.source_content_aspect = name


RESPONSE_HANDLERS: dict[str, Callable[[LumagenState, list[str]], None]] = {
    "S01": _handle_device_id,
    "S02": _handle_power,
    "I00": _handle_input_info,
    "I20": _handle_aspect_mode,
    "I21": _handle_full_info,
    "I22": _handle_full_info,
    "I23": _handle_full_info,
    "I24": _handle_full_info,
    "I25": _handle_full_info,
    "I53": _handle_game_mode,
    "I54": _handle_auto_aspect,
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
        self._state_waiters: list[
            tuple[asyncio.Event, Callable[[LumagenState], bool]]
        ] = []
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
        tasks = [
            t
            for t in (self._reconnect_task, self._keepalive_task, self._read_task)
            if t and not t.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
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
            self.state.clear_changed()
            self.state.power = "on"
            if self.state._changed:
                self._notify_state_changed()
            return
        if "POWER OFF" in line:
            self.state.clear_changed()
            self.state.power = "off"
            if self.state._changed:
                self._notify_state_changed()
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
                self.state.clear_changed()
                handler(self.state, fields)
                # Always notify on I2x — even unchanged values are
                # authoritative and must clear optimistic entity state.
                if self.state._changed or name in (
                    "I21",
                    "I22",
                    "I23",
                    "I24",
                    "I25",
                ):
                    self._notify_state_changed()
            except Exception:
                _LOGGER.debug("Error in handler for %s", name, exc_info=True)

    def _handle_label_response(self, line: str, match: re.Match[str]) -> None:
        """Extract label text and correlate with the pending query."""
        rest = line[match.end() :]  # everything after "!S1<cat>,"

        # A subsequent response may be concatenated after the label text.
        # Split on '!' which marks the start of the next response.
        next_bang = rest.find("!")
        if next_bang >= 0:
            label_text = rest[:next_bang]
            self._process_line(rest[next_bang:])
        else:
            # Labels are max 10 chars; truncate to avoid swallowing
            # concatenated response data that lacks a '!' delimiter.
            label_text = rest[:10]

        # Determine which label ID this is for
        label_id = self._pending_label_id
        if not label_id:
            # Try to extract the full XY from the echoed query before the '!'
            echo = line[: match.start()]
            if id_match := re.search(r"S1(\w{2})", echo):
                label_id = id_match.group(1)

        if label_id:
            self._last_label_value = label_text
        if self._label_event and label_id == self._pending_label_id:
            self._label_event.set()

    # -- Keepalive ----------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        """Probe connection after 30 s of idle.

        When the device is on, poll with ZQI25 (full signal state).
        When off, poll with ZQS02 (power status).
        """
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
            # Pick probe based on power state
            before = self._last_recv
            try:
                if self.state.power == "on":
                    await self.send_command("ZQI25")
                else:
                    await self.send_command("ZQS02")
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
                await self._handle_disconnect()

    def _notify_state_changed(self) -> None:
        if self._on_state_changed:
            self._on_state_changed()
        if self._state_waiters:
            for event, predicate in self._state_waiters:
                if predicate(self.state):
                    event.set()

    async def wait_for(
        self,
        predicate: Callable[[LumagenState], bool],
        timeout: float = 5.0,
    ) -> bool:
        """Wait until predicate(state) is true, or timeout. Returns success."""
        if predicate(self.state):
            return True
        event = asyncio.Event()
        waiter = (event, predicate)
        self._state_waiters.append(waiter)
        try:
            await asyncio.wait_for(event.wait(), timeout)
            return True
        except TimeoutError:
            return False
        finally:
            self._state_waiters.remove(waiter)

    # -- State queries ------------------------------------------------------

    async def fetch_identity(self) -> None:
        """Query device identity (model, firmware, serial)."""
        await self.send_command("ZQS01")

    async def fetch_power(self) -> None:
        """Query power state."""
        await self.send_command("ZQS02")

    async def fetch_runtime_state(self) -> None:
        """Query signal info (incl. input memory). Startup & power-on."""
        await self.send_command("ZQI25")

    async def fetch_full_state(self) -> None:
        """Query identity, power, signal info, and config state."""
        await self.fetch_identity()
        await self.fetch_power()
        await self.fetch_runtime_state()
        await self.send_command("ZQI53")
        await self.send_command("ZQI54")

    async def reload_config(self) -> int:
        """Re-fetch identity, config state, and all labels.

        Returns the number of labels that failed to resolve (0 = success).
        """
        await self.fetch_identity()
        await self.send_command("ZQI53")
        await self.send_command("ZQI54")
        return await self.get_labels()

    async def get_labels(self) -> int:
        """Query all labels (inputs A0-D7, custom modes, CMS, styles).

        Populates the per-category state fields and returns the number of
        labels that failed to resolve (0 = complete success).
        """
        all_labels: dict[str, str] = {}
        expected = 0

        # Input labels: A0-D7 (reverse iteration works around firmware bug)
        for mem in "ABCD":
            for i in reversed(range(10)):
                expected += 1
                label_id = f"{mem}{i}"
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
        """Return ordered source labels for the current input memory.

        Labels are stored per input memory at indices 0-9, where label
        index 0 = logical input 1, index 9 = logical input 10.
        """
        mem = self.state.input_memory or "A"
        return [
            f"{self.state.input_labels.get(f'{mem}{i}', 'Input')} ({i + 1})"
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
        else:
            return
        self.state.clear_changed()
        self.state.logical_input = number
        if self.state._changed:
            self._notify_state_changed()

    async def select_memory(self, memory: InputMemory) -> None:
        """Select input memory (A / B / C / D, case-insensitive)."""
        upper = memory.upper()
        if upper not in ("A", "B", "C", "D"):
            raise ValueError(f"Invalid input memory: {memory!r}")
        await self.send_command(upper.lower())
        self.state.clear_changed()
        self.state.input_memory = cast("InputMemory", upper)
        if self.state._changed:
            self._notify_state_changed()

    async def set_aspect(self, aspect: str) -> None:
        """Set source aspect ratio by display name.

        Selecting "Auto" enables auto aspect detection; any other
        selection (including NLS variants) disables it.

        For single-command aspects, we set optimistic state immediately.
        For NLS (two-command sequence), we skip optimistic state because
        the device fires an intermediate I24 after the base aspect
        command that would overwrite it.  Instead we let the final I24
        (after the NLS command) provide the authoritative state.
        """
        cmds = ASPECT_COMMANDS.get(aspect)
        if cmds is None:
            _LOGGER.warning("Unknown aspect ratio: %s", aspect)
            return
        for cmd in cmds:
            await self.send_command(cmd)
        is_nls = aspect.endswith("NLS")
        if not is_nls:
            self.state.clear_changed()
            if aspect == "Auto":
                self.state.nls_active = False
                self.state.auto_aspect = True
            else:
                self.state.nls_active = False
                self.state.source_content_aspect = aspect
                self.state.auto_aspect = False
            if self.state._changed:
                self._notify_state_changed()
        # Query authoritative state from device
        await self.send_command("ZQI54")
        await self.send_command("ZQI25")

    async def send_remote_command(self, command: str) -> None:
        """Send a named remote-control command."""
        cmd = REMOTE_COMMANDS.get(command.lower())
        if cmd is None:
            _LOGGER.warning("Unknown remote command: %s", command)
            return
        await self.send_command(cmd)

    # -- OSD ----------------------------------------------------------------

    @staticmethod
    def _sanitize_osd_text(text: str) -> str:
        """Strip characters outside the legal OSD range (0x20-0x7A)."""
        return "".join(c for c in text if 0x20 <= ord(c) <= 0x7A)

    async def show_osd_message(
        self,
        line_one: str,
        line_two: str = "",
        duration: int = 3,
        block_char: str = "",
    ) -> None:
        """Show an OSD message.

        *line_one*/*line_two*: up to 30 chars each (truncated with warning).
          Legal characters are ' ' through 'z' (0x20-0x7A); others are
          stripped.  ``{`` and ``\\r`` both terminate the message, so ``{``
          is implicitly excluded by the legal range.
        *duration*: 1-8 for that many seconds, 0 for persistent (until cleared).
        *block_char*: single character (0x20-0x7A) remapped to █ via ``ZB``.
          The Lumagen renders any extended-ASCII character as a solid block;
          ``ZB`` temporarily promotes the given character into that range.
        """
        if block_char and (
            len(block_char) != 1 or not (0x20 <= ord(block_char) <= 0x7A)
        ):
            raise ValueError(
                f"block_char must be a single character in 0x20-0x7A, "
                f"got {block_char!r}"
            )

        line_one = self._sanitize_osd_text(line_one)
        line_two = self._sanitize_osd_text(line_two)

        max_line = 30
        if len(line_one) > max_line:
            _LOGGER.warning("line_one truncated to %d chars", max_line)
            line_one = line_one[:max_line]
        if len(line_two) > max_line:
            _LOGGER.warning("line_two truncated to %d chars", max_line)
            line_two = line_two[:max_line]

        # 0 = persistent (protocol digit 9), 1-8 = seconds
        digit = 9 if duration == 0 else max(1, min(8, duration))
        payload = f"{line_one}\n{line_two}" if line_two else line_one
        prefix = f"ZB{block_char}" if block_char else ""
        await self.send_command(f"{prefix}ZT{digit}{payload}\r")

    async def show_osd_volume_bar(self, volume: float) -> None:
        """Show a volume bar on the OSD.

        Uses ZBX to set the block character (█), then ZT1 to display for 1s.
        Format: ``vol  ████████████████         `` (4-char number + 25-char bar).
        Bar is scaled for volume range 0-80.
        """
        bar_width = 25
        vol_limit = 80
        bar = "X" * int(min(volume, vol_limit) / vol_limit * bar_width)
        vol = f"{volume:.1f}" if volume < 100 else "max"
        await self.send_command(f"ZBXZT1{vol:>4} {bar:{bar_width}}\r")

    async def clear_osd_message(self) -> None:
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
        for name, val in (("mode", mode), ("cms", cms), ("style", style)):
            if val is not None and not 0 <= val <= 7:
                raise ValueError(f"{name} must be 0-7, got {val}")
        m = str(mode) if mode is not None else "K"
        c = str(cms) if cms is not None else "K"
        s = str(style) if style is not None else "K"
        await self.send_command(f"ZY530{m}{c}{s}\r")
        await self.send_command("ZQI25")

    async def previous_input(self) -> None:
        """Switch to the previous input."""
        await self.send_command("P")

    async def display_input_aspect(self) -> None:
        """Pop up input and aspect info on the OSD."""
        await self.send_command("ZY811\r")

    async def set_min_fan_speed(self, speed: int) -> None:
        """Set minimum fan speed (1-10)."""
        if not 1 <= speed <= 10:
            raise ValueError(f"Fan speed must be 1-10, got {speed}")
        await self.send_command(f"ZY552{speed - 1}\r")

    async def set_subtitle_shift(self, level: int) -> None:
        """Set subtitle shift (0=off, 1=3%, 2=6%)."""
        if level not in (0, 1, 2):
            raise ValueError(f"Subtitle shift must be 0-2, got {level}")
        await self.send_command(f"ZY553{level}\r")

    async def set_auto_aspect(self, enabled: bool) -> None:
        """Enable or disable auto aspect detection."""
        await self.send_command("~" if enabled else "V")
        await self.send_command("ZQI54")

    async def set_game_mode(self, enabled: bool) -> None:
        """Enable or disable game mode."""
        await self.send_command(f"ZY551{'1' if enabled else '0'}\r")
        await self.send_command("ZQI53")

    # -- Labels -------------------------------------------------------------

    async def set_label(self, category: LabelCategory, index: int, text: str) -> None:
        """Set a label on the device.

        *category*: 'A'-'D' (input per input memory), '0' (all input memories),
                    '1' (custom mode), '2' (CMS), '3' (style).
        *index*: label index (0-7 for all categories).
        *text*: label text (max 10 for inputs, 7 for custom modes,
                8 for CMS/styles).
        """
        if category not in ("A", "B", "C", "D", "0", "1", "2", "3"):
            raise ValueError(f"Invalid label category: {category!r}")
        max_index = 9 if category in ("A", "B", "C", "D", "0") else 7
        if not 0 <= index <= max_index:
            raise ValueError(
                f"Label index must be 0-{max_index} for category"
                f" {category!r}, got {index}"
            )
        max_len = (
            10 if category in ("A", "B", "C", "D", "0") else 7 if category == "1" else 8
        )
        if not text.isascii():
            raise ValueError("Label text must be ASCII only")
        if len(text) > max_len:
            raise ValueError(f"Label text must be <={max_len} chars, got {len(text)}")
        await self.send_command(f"ZY524{category}{index}{text}\r")
        # Re-fetch to confirm; use the sent text as the authoritative
        # value since the device may truncate and the response can have
        # concatenated protocol data that corrupts the label text.
        label_id = f"{category}{index}"
        await self._query_label(label_id)
        label_text = text
        # Update the appropriate label dict
        if category in ("A", "B", "C", "D"):
            self.state.input_labels[label_id] = label_text
        elif category == "0":
            # Category 0 sets all input memories at once
            for mem in "ABCD":
                self.state.input_labels[f"{mem}{index}"] = label_text
        elif category == "1":
            self.state.custom_mode_labels[label_id] = label_text
        elif category == "2":
            self.state.cms_labels[label_id] = label_text
        elif category == "3":
            self.state.style_labels[label_id] = label_text
        self._notify_state_changed()

    # -- Misc ---------------------------------------------------------------

    async def save_config(self) -> None:
        """Save current configuration to flash."""
        await self.send_command("ZY6SAVECONFIG\r")

    async def trigger_hotplug(self, input_num: int | None = None) -> None:
        """Toggle HDMI hotplug on an input (or all inputs if None)."""
        target = str(input_num) if input_num is not None else "A"
        await self.send_command(f"ZY520{target}\r")
