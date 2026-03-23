# pyright: reportUnusedFunction=false
"""Async TCP client for Lumagen Radiance Pro."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import ClassVar, Literal, cast, get_args

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

InputMemory = Literal["A", "B", "C", "D"]
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


# ASPECT_COMMANDS maps each AR to the RS232 command for that ratio. In cases
# where there's more than one RS232 variant (e.g. "previous zoom" vs "no zoom"),
# we use the same command the physical remote control sends.
ASPECT_COMMANDS: dict[str, str] = {
    "Auto": "~",
    "Letterbox": "l",
    "1.33": "n",
    "1.37": "+l",
    "1.78": "w",
    "1.85": "j",
    "1.90": "A",
    "2.00": "C",
    "2.10": "+j",
    "2.20": "E",
    "2.35": "W",
    "2.40": "G",
    "2.55": "+W",
    "2.76": "+N",
}

# REMOTE_COMMANDS maps buttons on the physical extended remote to the RS232 command.
# The keys in this dict essentially match what's silk-screened on the remote.
REMOTE_COMMANDS: dict[str, str] = {
    # Digits and power/standby
    "on": "%",
    **{str(i): str(i) for i in range(10)},
    "10+": "+",
    "stby": "$",
    # Navigation
    "clear": "!",
    "help": "U",
    "exit": "X",
    "menu": "M",
    "up": "^",
    "down": "v",
    "left": "<",
    "right": ">",
    "ok": "k",
    "hdr_setup": "Y",
    # Input selection
    "input": "i",
    "zone": "L",
    "alt": "#",
    "prev": "P",
    # Aspect ratios
    "4:3": "n",
    "16:9": "w",
    "1.85": "j",
    "2.00": "C",
    "2.20": "E",
    "2.40": "G",
    # Source aspect ratio
    "lbox": "l",
    "1.90": "A",
    "2.35": "W",
    "nls": "N",
    # Memory selection
    "a": "a",
    "b": "b",
    "c": "c",
    "d": "d",
    # Bottom row
    "auto_aspect_disable": "V",
    "auto_aspect_enable": "~",
    "pattern": "H",
    "save": "S",
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

# Regex for responses: !<3-char code>,<fields>
# Code is a letter followed by two alphanumeric characters (e.g. S01, I21,
# S1A for labels).
_RESPONSE_RE = re.compile(r"!([A-Z][A-Z0-9]{2}),(.*)")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class LabelDict(dict[str, str]):
    """Dict that logs and tracks mutations like LumagenState.__setattr__.

    Each ``__setitem__`` call that changes a value emits a debug log and
    sets ``_dirty``.  ``LumagenState.clear_changed`` resets the flag.
    """

    __slots__ = ("_dirty",)

    def __init__(self) -> None:
        super().__init__()
        self._dirty = False

    def __setitem__(self, key: str, value: str) -> None:
        old = self.get(key)
        if old != value:
            _LOGGER.debug("state: labels[%s]: %r -> %r", key, old, value)
            self._dirty = True
        super().__setitem__(key, value)


@dataclass
class LumagenState:
    """Flat device state, updated in place by response handlers.

    Tracks field-level changes via ``__setattr__`` and ``LabelDict``.
    Any assignment that actually modifies a value emits a debug log line.
    Callers should call ``clear_changed()`` before a batch of updates and
    inspect ``changed`` afterward to decide whether to notify listeners.
    """

    # Connection
    connected: bool = False

    # Identity (S01: model, sw_rev, model#, serial#)
    model_name: str | None = None
    software_revision: str | None = None
    model_number: str | None = None
    serial_number: str | None = None

    # Power
    power: bool | None = None

    # Input
    logical_input: int | None = None
    input_memory: InputMemory | None = None
    physical_input: int | None = None
    input_config_number: int | None = None

    # Video status
    input_video_status: InputVideoStatus | None = None

    # Source
    source_content_aspect: str | None = None  # "1.33", "1.78", "2.40", …
    source_raster_aspect: str | None = None
    detected_content_aspect: str | None = None
    detected_raster_aspect: str | None = None
    source_dynamic_range: DynamicRange | None = None
    source_mode: SourceMode | None = None
    source_3d_mode: ThreeDMode | None = None
    source_vertical_rate: int | None = None
    source_vertical_resolution: int | None = None
    nls: bool | None = None

    # Output
    output_vertical_rate: int | None = None
    output_vertical_resolution: int | None = None
    output_cms: int | None = None
    output_style: int | None = None
    output_colorspace: OutputColorspace | None = None
    output_aspect: str | None = None
    output_3d_mode: ThreeDMode | None = None
    output_mode: OutputMode | None = None
    outputs_on: int | None = None  # raw bitmask from WWWW field

    # Config
    auto_aspect: bool | None = None

    # Labels (populated by _query_labels / set_label)
    _labels: LabelDict = field(default_factory=LabelDict)

    # Change tracking (not part of equality/repr)
    _dirty: bool = field(default=False, init=False, repr=False, compare=False)

    # -- Derived properties -------------------------------------------------

    @property
    def source_aspect(self) -> str | None:
        """Content aspect with Letterbox detection.

        When raster is 1.33 (4:3) and content is 1.78 (16:9), the source
        is a letterboxed 16:9 image inside a 4:3 frame.
        """
        if self.source_raster_aspect == "1.33" and self.source_content_aspect == "1.78":
            return "Letterbox"
        return self.source_content_aspect

    @property
    def input_label(self) -> str | None:
        """Label for the current logical input and memory."""
        if self.logical_input is None:
            return None
        mem = self.input_memory or "A"
        return self._labels.get(f"{mem}{self.logical_input - 1}")

    @property
    def cms_label(self) -> str | None:
        """Label for the current output CMS."""
        if self.output_cms is None:
            return None
        return self._labels.get(f"2{self.output_cms}")

    @property
    def style_label(self) -> str | None:
        """Label for the current output style."""
        if self.output_style is None:
            return None
        return self._labels.get(f"3{self.output_style}")

    def labels_by_prefix(self, prefix: str) -> dict[str, str]:
        """Return sorted labels whose key starts with *prefix*."""
        return {k: v for k, v in sorted(self._labels.items()) if k[0] == prefix}

    # -- Change tracking ----------------------------------------------------

    def __setattr__(self, name: str, value: object) -> None:
        try:
            old = object.__getattribute__(self, name)
        except AttributeError:
            pass  # Initial assignment during __init__
        else:
            if old != value and not name.startswith("_"):
                _LOGGER.debug("state: %s: %r -> %r", name, old, value)
                self.__dict__["_dirty"] = True
        object.__setattr__(self, name, value)

    @property
    def changed(self) -> bool:
        """True if any field or label was modified since last clear."""
        return self._dirty or self._labels._dirty  # pyright: ignore[reportPrivateUsage]

    def clear_changed(self) -> None:
        """Reset change-tracking flags."""
        self.__dict__["_dirty"] = False
        self._labels._dirty = False  # pyright: ignore[reportPrivateUsage]

    # -- Serialization ------------------------------------------------------

    _STORED_FIELDS: ClassVar[tuple[str, ...]] = (
        "model_name",
        "software_revision",
        "model_number",
        "serial_number",
    )

    def to_stored_dict(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot of persistent state."""
        data: dict[str, object] = {k: getattr(self, k) for k in self._STORED_FIELDS}
        data["labels"] = dict(self._labels)
        return data

    def load_stored_dict(self, data: dict[str, object]) -> None:
        """Restore persistent state from a dict (e.g. loaded from disk)."""
        for key in self._STORED_FIELDS:
            if key in data:
                setattr(self, key, data[key])
        if "labels" in data:
            self._labels.update(data["labels"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(s: str, base: int = 10) -> int | None:
    """Parse an int, returning None on failure."""
    with suppress(ValueError):
        return int(s, base)
    return None


def _safe_aspect(code: str) -> str:
    """Convert numeric aspect code ('240') to display name ('2.40')."""
    val = _safe_int(code) or 0
    return f"{val / 100:.2f}"


# ---------------------------------------------------------------------------
# Response handlers — mutate state directly; changes tracked by __setattr__
# Return True to force notification even if state hasn't changed
# ---------------------------------------------------------------------------

_RESPONSE_HANDLERS: dict[str, Callable[[LumagenState, list[str]], bool | None]] = {}


def _on(
    *codes: str,
) -> Callable[
    [Callable[[LumagenState, list[str]], bool | None]],
    Callable[[LumagenState, list[str]], bool | None],
]:
    """Register a function as the handler for one or more response codes."""

    def decorator(
        fn: Callable[[LumagenState, list[str]], bool | None],
    ) -> Callable[[LumagenState, list[str]], bool | None]:
        for code in codes:
            _RESPONSE_HANDLERS[code] = fn
        return fn

    return decorator


@_on("S01")
def _on_device_id(state: LumagenState, fields: list[str]) -> None:
    """S01 — model, sw_revision, model_number, serial_number."""
    if len(fields) < 4:
        return
    state.model_name = fields[0]
    state.software_revision = fields[1]
    state.model_number = fields[2]
    state.serial_number = fields[3]


@_on("S02")
def _on_power(state: LumagenState, fields: list[str]) -> None:
    """S02 — 0 = standby, 1 = active."""
    if not fields:
        return
    state.power = fields[0] == "1"


@_on("I00")
def _on_input_info(state: LumagenState, fields: list[str]) -> None:
    """I00 — logical input, input memory, physical input."""
    if len(fields) < 3:
        return
    state.logical_input = _safe_int(fields[0])
    state.input_memory = cast("InputMemory", fields[1])
    state.physical_input = _safe_int(fields[2])


@_on("I21", "I22", "I23", "I24", "I25")
def _on_full_info(state: LumagenState, fields: list[str]) -> bool:
    """I21/I22/I23/I24/I25 — full device info.

    Field indices (0-based after splitting on commas):
      0=M  1=RRR  2=VVVV  3=D  4=X  5=AAA  6=SSS  7=Y  8=T  9=WWWW
      10=C 11=B   12=PPP  13=QQQQ 14=ZZZ
      15=E 16=F   17=G    18=H          (v2+)
      19=II 20=KK                       (v3+)
      21=JJJ 22=LLL                     (v4+)
      23=MEM 24=PWR                       (v5)

    Fields are ordered by protocol version. We parse as many as are present.
    """
    notify = False

    # I21: v1 fields (0-14)
    if len(fields) < 15:
        return notify

    # Always notify on any valid I2x — even unchanged values are
    # authoritative and must clear optimistic entity state.
    notify = True

    state.input_video_status = _INPUT_VIDEO_STATUS.get(fields[0])
    state.source_vertical_rate = _safe_int(fields[1])
    state.source_vertical_resolution = _safe_int(fields[2])
    state.source_3d_mode = _3D_MODE.get(fields[3])
    state.input_config_number = _safe_int(fields[4])
    state.source_raster_aspect = _safe_aspect(fields[5])
    state.source_content_aspect = _safe_aspect(fields[6])
    state.nls = fields[7] == "N"
    state.output_3d_mode = _3D_MODE.get(fields[8])
    state.outputs_on = _safe_int(fields[9], base=16)
    state.output_cms = _safe_int(fields[10])
    state.output_style = _safe_int(fields[11])
    state.output_vertical_rate = _safe_int(fields[12])
    state.output_vertical_resolution = _safe_int(fields[13])
    state.output_aspect = _safe_aspect(fields[14])

    # I22: v2 fields (15-18)
    if len(fields) < 19:
        return notify
    state.output_colorspace = _OUTPUT_COLORSPACE.get(fields[15])
    state.source_dynamic_range = _DYNAMIC_RANGE.get(fields[16])
    state.source_mode = _SOURCE_MODE.get(fields[17])
    state.output_mode = _OUTPUT_MODE.get(fields[18])

    # I23: v3 fields (19-20) — II (virtual/logical input), KK (physical input)
    if len(fields) < 21:
        return notify
    state.logical_input = _safe_int(fields[19])
    state.physical_input = _safe_int(fields[20])

    # I24: v4 fields (21-22) — detected raster/content aspect
    if len(fields) < 23:
        return notify
    state.detected_raster_aspect = _safe_aspect(fields[21])
    state.detected_content_aspect = _safe_aspect(fields[22])

    # I25: v5 fields (23-24) — input memory, power status
    if len(fields) < 25:
        return notify
    mem = fields[23]
    if mem in get_args(InputMemory):
        state.input_memory = cast("InputMemory", mem)
    state.power = fields[24] == "1"
    return notify


@_on("I54")
def _on_auto_aspect(state: LumagenState, fields: list[str]) -> None:
    """I54 — auto aspect status (fw ≥041824)."""
    if not fields:
        return
    state.auto_aspect = fields[0] == "1"


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
        self._read_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._running = False
        self._disconnecting = False
        self._on_state_changed: Callable[[], None] | None = None
        self._on_connection_changed: Callable[[bool], None] | None = None
        self._last_recv: float = 0.0
        self._write_lock = asyncio.Lock()
        self._label_lock = asyncio.Lock()
        self._pending_label_event: asyncio.Event | None = None
        self._pending_label_text: str | None = None
        for code in ("S1A", "S1B", "S1C", "S1D", "S11", "S12", "S13"):
            _RESPONSE_HANDLERS[code] = self._on_label
        self._last_power: bool | None = None
        self._power_on_task: asyncio.Task[None] | None = None
        self._state_waiters: list[
            tuple[asyncio.Event, Callable[[LumagenState], bool]]
        ] = []

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
            for t in (
                self._reconnect_task,
                self._keepalive_task,
                self._read_task,
                self._power_on_task,
            )
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
        self.state.power = None
        self.state.connected = True
        self._read_task = asyncio.create_task(self._read_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        if self._on_connection_changed:
            self._on_connection_changed(True)

    async def _on_disconnect(self) -> None:
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
            self._notify_listeners()

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
                await self.query_runtime()
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
                    self._on_readline(text)
            except asyncio.CancelledError:
                return
            except (OSError, ConnectionError):
                break
            except Exception:
                _LOGGER.exception("Read loop error")
                break

        if self._running:
            await self._on_disconnect()

    def _on_readline(self, line: str) -> None:
        """Parse a single line from the TCP stream."""
        # Special power messages
        if "Power-up complete" in line:
            self.state.clear_changed()
            self.state.power = True
            if self.state.changed:
                self._notify_listeners()
            return
        if "POWER OFF" in line:
            self.state.clear_changed()
            self.state.power = False
            if self.state.changed:
                self._notify_listeners()
            return

        # Response: !<code>,<fields>
        match = _RESPONSE_RE.search(line)
        if not match:
            return

        name, fields = match.groups()
        if name not in _RESPONSE_HANDLERS:
            return

        self.state.clear_changed()
        notify = False
        try:
            notify = _RESPONSE_HANDLERS[name](self.state, fields.split(","))
        except Exception:
            _LOGGER.exception("Error in handler for %s", name)
        else:
            if self.state.changed or notify:
                self._notify_listeners()

    # -- Keepalive ----------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        """Probe connection after 30 s of idle.

        Uses query_runtime which pipelines ZQI25+ZQI54 when the device
        is on and sends ZQS02 when off.
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
            before = self._last_recv
            try:
                await self.query_runtime()
                await asyncio.sleep(probe_timeout)
            except asyncio.CancelledError:
                return
            if self._last_recv == before:
                _LOGGER.warning("Keepalive timeout — reconnecting")
                await self._on_disconnect()
                return

    # -- Sending ------------------------------------------------------------

    async def send_raw_command(self, cmd: str) -> None:
        """Send an arbitrary RS232 command string (public, for debug tools)."""
        await self._send_command(cmd)

    async def _send_command(self, cmd: str) -> None:
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
                await self._on_disconnect()

    def _notify_listeners(self) -> None:
        """Notify state-change callback and wake any wait_for waiters.

        Called in two ways:
        1. From _on_readline — after a response handler runs, guarded by
           ``if self.state.changed or notify``.  Only fires when a field
           actually changed or the handler explicitly requested it.
        2. Explicitly — by query_config (label responses bypass _on_readline)
           and by _on_disconnect.  These calls are unconditional because the
           caller knows state has changed in bulk.
        """
        power = self.state.power
        if power and not self._last_power:
            # None → True: first connect, device already on — query immediately
            # False → True: device just powered on — wait 10s to settle
            self._schedule_power_on_refresh(delay=self._last_power is not None)
        if power is not None:
            self._last_power = power

        if self._on_state_changed:
            self._on_state_changed()
        if self._state_waiters:
            for event, predicate in self._state_waiters:
                if predicate(self.state):
                    event.set()

    def _schedule_power_on_refresh(self, *, delay: bool = True) -> None:
        """Schedule a runtime state refresh after discovering device is on.

        *delay=True* (default) waits 10 s for the device to settle after a
        real power-on.  *delay=False* queries immediately — used when we
        first connect and discover the device is already on.
        """
        if self._power_on_task and not self._power_on_task.done():
            self._power_on_task.cancel()
        self._power_on_task = asyncio.create_task(self._power_on_refresh(delay=delay))

    async def _power_on_refresh(self, *, delay: bool = True) -> None:
        """Re-query runtime state after power-on or first connect."""
        if delay:
            _LOGGER.info("Power on detected — refreshing state in 10s")
            await asyncio.sleep(10)
        else:
            _LOGGER.info("Device already on — querying runtime state")
        try:
            await self.query_runtime()
        except Exception:
            _LOGGER.exception("Error querying state after power-on")

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

    async def query_runtime(self) -> None:
        """Query runtime state (fire-and-forget).

        When on: pipelines ZQI25 + ZQI54 (signal info, auto aspect).
        When off/unknown: sends ZQS02 (power status only — signal fields
        are stale in standby).
        """
        if self.state.power:
            await self._send_command("ZQI25ZQI54")
        else:
            await self._send_command("ZQS02")

    async def query_config(self) -> bool:
        """Refresh identity and labels from device.

        Sends ZQS01 (identity), waits for the response, then queries all
        labels sequentially.  Returns True if both identity and all labels
        were resolved.
        """
        # Clear model name so we know ZQS01 is successful, but save it first
        # in case ZQS01 fails so we can restore it to what it was.
        model_name = self.state.model_name
        self.state.model_name = None
        await self._send_command("ZQS01")
        if not await self.wait_for(lambda s: s.model_name is not None):
            self.state.model_name = model_name
            return False
        labels_ok = await self._query_labels()
        # Explicit notification: label responses go through _on_label
        # (event-based correlation), not _on_readline's normal notify
        # path.  The S01 identity response does flow through _on_readline
        # but arrives early and may already have been notified.  This
        # ensures listeners see the complete config state.
        self._notify_listeners()
        return labels_ok

    # -- Labels -------------------------------------------------------------

    def get_source_list(self) -> list[str]:
        """Return ordered source labels for the current input memory.

        Labels are stored per input memory at indices 0-9, where label
        index 0 = logical input 1, index 9 = logical input 10.
        """
        mem = self.state.input_memory or "A"
        return [
            f"{self.state._labels.get(f'{mem}{i}', 'Input')} ({i + 1})"  # pyright: ignore[reportPrivateUsage]
            for i in range(10)
        ]

    def _on_label(self, _state: LumagenState, fields: list[str]) -> None:
        """S1x — label text (input memories A-D, custom mode, CMS, style).

        Registered into _RESPONSE_HANDLERS at init time so that label
        responses can update client-owned correlation state directly.
        """
        if not self._pending_label_event:
            _LOGGER.debug("Ignoring unsolicited label response: %s", ",".join(fields))
            return
        self._pending_label_text = ",".join(fields)
        self._pending_label_event.set()

    async def _query_label(self, category: LabelCategory, index: int) -> bool:
        """Query a single label and store the result.

        Returns True if the label was resolved, False on timeout.
        """
        label_id = f"{category}{index}"
        async with self._label_lock:
            self._pending_label_event = asyncio.Event()
            self._pending_label_text = None
            await self._send_command(f"ZQS1{label_id}")
            try:
                await asyncio.wait_for(self._pending_label_event.wait(), timeout=5.0)
            except TimeoutError:
                _LOGGER.debug("Timeout waiting for label %s", label_id)
                return False
            finally:
                self._pending_label_event = None

            text = self._pending_label_text
            if text is None:
                _LOGGER.warning("Label %s event fired but text was never set", label_id)
                return False

            if category == "0":
                for mem in "ABCD":
                    self.state._labels[f"{mem}{index}"] = text  # pyright: ignore[reportPrivateUsage]
            else:
                self.state._labels[label_id] = text  # pyright: ignore[reportPrivateUsage]
            return True

    async def _query_labels(self) -> bool:
        """Query all labels (inputs A0-D9, custom modes, CMS, styles).

        Returns True if all labels were resolved, False on first failure.
        """
        # Input labels: A0-D9 (reverse iteration works around firmware bug)
        for c in ("A", "B", "C", "D"):
            for i in reversed(range(10)):
                if not await self._query_label(c, i):
                    return False

        # Custom mode (1), CMS (2), Style (3) labels: X0-X7
        for c in ("1", "2", "3"):
            for i in range(8):
                if not await self._query_label(c, i):
                    return False

        return True

    async def set_label(self, category: LabelCategory, index: int, text: str) -> None:
        """Set a label on the device.

        *category*: 'A'-'D' (input per input memory), '0' (all input memories),
                    '1' (custom mode), '2' (CMS), '3' (style).
        *index*: label index (0-9 for inputs, 0-7 for others).
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
        await self._send_command(f"ZY524{category}{index}{text}\r")
        if await self._query_label(category, index):
            self._notify_listeners()

    # -- Convenience commands -----------------------------------------------

    async def power_on(self) -> None:
        """Power on the device."""
        await self._send_command("%")

    async def power_off(self) -> None:
        """Power off (standby)."""
        await self._send_command("$")

    async def select_input(self, number: int) -> None:
        """Select a logical input by number (1-19).

        Physical HDMI port count varies by model (1-10), but logical
        (virtual) inputs can go up to 19.  RS232 protocol: ``i1``-``i9``
        for inputs 1-9, ``i+0``-``i+9`` for inputs 10-19.
        """
        if 1 <= number <= 9:
            await self._send_command(f"i{number}")
        elif 10 <= number <= 19:
            await self._send_command(f"i+{number - 10}")
        else:
            return
        self.state.clear_changed()
        self.state.logical_input = number
        if self.state.changed:
            self._notify_listeners()

    async def select_memory(self, memory: InputMemory) -> None:
        """Select input memory (A / B / C / D)."""
        if memory not in get_args(InputMemory):
            raise ValueError(f"Invalid input memory: {memory!r}")
        await self._send_command(memory.lower())
        self.state.clear_changed()
        self.state.input_memory = memory
        if self.state.changed:
            self._notify_listeners()

    async def set_aspect(self, aspect: str) -> None:
        """Set source aspect ratio by display name.

        Selecting "Auto" enables auto aspect detection; any other
        selection disables it.
        """
        cmd = ASPECT_COMMANDS.get(aspect)
        if cmd is None:
            _LOGGER.warning("Unknown aspect ratio: %s", aspect)
            return
        await self._send_command(cmd)
        self.state.clear_changed()
        if aspect == "Auto":
            self.state.nls = False
            self.state.auto_aspect = True
        else:
            self.state.nls = False
            self.state.source_content_aspect = aspect
            self.state.auto_aspect = False
        if self.state.changed:
            self._notify_listeners()
        # Query authoritative state from device
        await self._send_command("ZQI54")
        await self._send_command("ZQI25")

    async def toggle_nls(self) -> None:
        """Toggle Non-Linear Stretch on or off."""
        await self._send_command("N")
        # Query authoritative state — NLS flag is in I25
        await self._send_command("ZQI25")

    async def send_remote_command(self, command: str) -> None:
        """Send a named remote-control command."""
        cmd = REMOTE_COMMANDS.get(command.lower())
        if cmd is None:
            _LOGGER.warning("Unknown remote command: %s", command)
            return
        await self._send_command(cmd)

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
        if not self.state.power:
            return

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
        payload = f"{line_one:<30}{line_two}" if line_two else line_one
        prefix = f"ZB{block_char}" if block_char else ""
        await self._send_command(f"{prefix}ZT{digit}{payload}\r")

    async def show_osd_volume_bar(self, level: float, label: str | None = None) -> None:
        """
        Show volume bar on the OSD.

        - level: level (0.0 - 1.0) which determines width of bar (0 - 24 blocks)
        - label: shown in front of volume bar instead of numeric level (5 chars max)

        The Lumagen can display two lines of 30 characters each. We show a single line
        using 5 characters for the label, a space, and the remaining 24 characters as
        a bar of block characters, like so:

            0        1         2         3
            123456789012345678901234567890
           +------------------------------+
           |63.5% ███████████████████     |
           +------------------------------+

        The message is displayed for 1 second.
        """
        if not self.state.power:
            return

        level = max(min(level, 1.0), 0)  # clamp to 0 - 1
        if label is None:
            if level == 0:
                label = "Min"
            elif level == 1:
                label = "Max"
            else:
                label = f"{level:.1%}"
        await self._send_command(f"ZBXZT1{label:<5.5} {'X' * int(level * 24):<24}\r")

    async def clear_osd_message(self) -> None:
        """Clear any OSD message."""
        if not self.state.power:
            return
        await self._send_command("ZC")

    async def set_auto_aspect(self, enabled: bool) -> None:
        """Enable or disable auto aspect detection."""
        await self._send_command("~" if enabled else "V")
        await self._send_command("ZQI54")

    # -- Misc ---------------------------------------------------------------

    async def save_config(self) -> None:
        """Save current configuration to flash."""
        await self._send_command("ZY6SAVECONFIG\r")

    async def restart_outputs(self) -> None:
        """Restart outputs via ALT, PREV remote sequence."""
        await self._send_command("#P")
