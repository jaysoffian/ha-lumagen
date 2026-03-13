#!/usr/bin/env -S uv run python
"""Textual TUI for exercising the Lumagen Radiance Pro TCP client."""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Input, RichLog, Static

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parent / "custom_components" / "ha_lumagen"),
)

from client import (
    ASPECT_COMMANDS,
    REMOTE_COMMANDS,
    LumagenClient,
    LumagenState,
)

# ---------------------------------------------------------------------------
# Instrumented client — captures raw protocol traffic
# ---------------------------------------------------------------------------


class CommandInput(Input):
    """Input with readline-style tab completion."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("tab", "complete", "Tab completion", show=False),
    ]

    def __init__(self, completions: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._completions = completions

    def action_complete(self) -> None:
        """Readline-style tab completion."""
        text = self.value.lower()
        if not text:
            return

        matches = [c for c in self._completions if c.lower().startswith(text)]
        if not matches:
            return

        if len(matches) == 1:
            # Unique match — complete it, add trailing space if it's a full command
            completed = matches[0]
            if not any(
                c.lower().startswith(completed.lower()) and c != completed
                for c in self._completions
            ):
                completed += " "
            self.value = completed
            self.cursor_position = len(self.value)
        else:
            # Multiple matches — complete the common prefix
            prefix = matches[0]
            for m in matches[1:]:
                while not m.lower().startswith(prefix.lower()):
                    prefix = prefix[:-1]
            if len(prefix) > len(text):
                self.value = prefix
                self.cursor_position = len(self.value)
            else:
                # Show options in the log
                log = self.app.query_one("#log", RichLog)
                log.write("[dim]  " + "  ".join(sorted(matches)) + "[/]")


class InstrumentedClient(LumagenClient):
    """LumagenClient subclass that emits send/receive events for the TUI."""

    def __init__(self) -> None:
        super().__init__()
        self._on_line_sent: list[Callable[[str], None]] = []
        self._on_line_received: list[Callable[[str], None]] = []

    async def send_command(self, cmd: str) -> None:
        for cb in self._on_line_sent:
            cb(cmd)
        await super().send_command(cmd)

    def _process_line(self, line: str) -> None:
        for cb in self._on_line_received:
            cb(line)
        super()._process_line(line)


# ---------------------------------------------------------------------------
# State panel widget
# ---------------------------------------------------------------------------


def _source_summary(s: LumagenState) -> str:
    if s.source_vertical_resolution is None:
        return "—"
    mode = (s.source_mode or "")[0:1].lower() if s.source_mode else ""
    rate = f" {s.source_vertical_rate}Hz" if s.source_vertical_rate else ""
    return f"{s.source_vertical_resolution}{mode}{rate}"


def _output_summary(s: LumagenState) -> str:
    if s.output_vertical_resolution is None:
        return "—"
    rate = f" {s.output_vertical_rate}Hz" if s.output_vertical_rate else ""
    return f"{s.output_vertical_resolution}p{rate}"


def _input_label(s: LumagenState) -> str:
    bank = s.input_memory or "A"
    idx = (s.logical_input or 1) - 1
    return s.input_labels.get(f"{bank}{idx}", "—")


def _input_summary(s: LumagenState) -> str:
    if s.logical_input is None:
        return "—"
    return f"{s.logical_input} (Memory {s.input_memory})"


def _physical_in(s: LumagenState) -> str:
    return str(s.physical_input) if s.physical_input is not None else "—"


def _output_mode(s: LumagenState) -> str:
    if s.output_mode is None:
        return "—"
    label = s.custom_mode_labels.get(f"1{s.output_mode}", f"Custom{s.output_mode + 1}")
    return f"{s.output_mode + 1}: {label}"


def _cms(s: LumagenState) -> str:
    if s.output_cms is None:
        return "—"
    cms = s.cms_labels.get(f"2{s.output_cms}", f"CMS{s.output_cms + 1}")
    return f"{s.output_cms + 1}: {cms}"


def _style(s: LumagenState) -> str:
    if s.output_style is None:
        return "—"
    style = s.style_labels.get(f"3{s.output_style}", f"Style{s.output_style + 1}")
    return f"{s.output_style + 1}: {style}"


_STATE_FIELDS: list[tuple[str, str, Callable[[LumagenState], str | None] | None]] = [
    ("Connected", "connected", lambda s: "Yes" if s.connected else "No"),
    (
        "Power",
        "power",
        lambda s: {"on": "On", "off": "Off"}.get(s.power or "", "—"),
    ),
    ("Model", "model_name", lambda s: s.model_name or "—"),
    ("Firmware", "software_revision", lambda s: s.software_revision or "—"),
    ("Serial", "serial_number", lambda s: s.serial_number or "—"),
    ("", "", None),  # spacer
    ("Input", "logical_input", _input_summary),
    ("Physical In", "physical_input", _physical_in),
    ("Input Label", "_input_label", _input_label),
    ("", "", None),
    ("Source", "_source_summary", _source_summary),
    ("Dynamic Range", "source_dynamic_range", lambda s: s.source_dynamic_range or "—"),
    (
        "Content Aspect",
        "source_content_aspect",
        lambda s: s.source_content_aspect or "—",
    ),
    ("Raster Aspect", "source_raster_aspect", lambda s: s.source_raster_aspect or "—"),
    ("NLS", "nls_active", lambda s: "Active" if s.nls_active else "Off"),
    ("", "", None),
    ("Output", "_output_summary", _output_summary),
    ("Output Aspect", "output_aspect", lambda s: s.output_aspect or "—"),
    ("Colorspace", "output_colorspace", lambda s: s.output_colorspace or "—"),
    ("Mode", "_output_mode", _output_mode),
    ("CMS", "_cms", _cms),
    ("Style", "_style", _style),
    ("Game Mode", "game_mode", lambda s: "On" if s.game_mode else "Off"),
]


class StatePanel(Static):
    """Displays current device state as a formatted table."""

    DEFAULT_CSS = """
    StatePanel {
        width: 1fr;
        padding: 1 2;
    }
    """

    def render_state(self, state: LumagenState) -> str:
        lines: list[str] = []
        for label, _key, fmt in _STATE_FIELDS:
            if fmt is None:
                lines.append("")
                continue
            val = fmt(state)
            lines.append(f"  {label + ':':<18s} {val}")
        return "\n".join(lines)

    def update_state(self, state: LumagenState) -> None:
        self.update(self.render_state(state))


# ---------------------------------------------------------------------------
# TUI app
# ---------------------------------------------------------------------------

HELP_TEXT = """\
[bold]Power & Input:[/]
  on / off               turn Lumagen on or off
  <1-19>                 select input
  a / b / c / d          select memory bank

[bold]Video Processing:[/]
  aspect <name>          source aspect (4:3, 16:9, 2.40, NLS, …)
  mode <1-8>             output custom mode
  cms <1-8>              output CMS
  style <1-8>            output style
  game on / off          game mode
  autoaspect on / off    auto aspect detection

[bold]Labels & OSD:[/]
  labels                 show all labels
  label <id> <text>      set label (e.g. label A1 Apple TV)
  osd \\[0-9] <text>       OSD message (0-8=seconds, 9=persistent; \\n for newline)
  osd                    clear OSD

[bold]Navigation & System:[/]
  remote <cmd>           remote key (menu, up, down, ok, exit, …)
  save                   save config to flash
  hotplug \\[input]        toggle HDMI hotplug (all inputs if omitted)
  refresh                re-query full state
  refresh labels         re-fetch labels from device
  help                   show this message
  quit / q               exit

[bold]Raw RS232:[/]
  Z...                   e.g. ZQS01, ZQI24, ZY530MCS

[bold]Keyboard shortcuts:[/]
  Ctrl+Q                 quit
  Ctrl+L                 clear protocol log
  Ctrl+R                 refresh state
"""

# All completable command prefixes for the suggester
_COMMAND_SUGGESTIONS = sorted(
    {
        "on",
        "off",
        *[f"aspect {a}" for a in ASPECT_COMMANDS],
        *[f"mode {i}" for i in range(1, 9)],
        *[f"cms {i}" for i in range(1, 9)],
        *[f"style {i}" for i in range(1, 9)],
        "game on",
        "game off",
        "autoaspect on",
        "autoaspect off",
        "labels",
        "label ",
        "osd ",
        *[f"remote {k}" for k in REMOTE_COMMANDS if not k.isdigit()],
        "save",
        "hotplug",
        "refresh",
        "refresh labels",
        "help",
        "quit",
        "exit",
    }
)


class LumagenTUI(App):
    """Textual TUI for the Lumagen Radiance Pro."""

    CSS = """
    #main {
        height: 1fr;
    }
    #state-panel {
        width: 40;
        border: solid $accent;
        border-title-color: $text;
    }
    #log-panel {
        width: 1fr;
        border: solid $accent;
        border-title-color: $text;
    }
    #log {
        scrollbar-size: 1 1;
    }
    #input-bar {
        dock: bottom;
        height: 3;
        padding: 0 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("ctrl+r", "refresh", "Refresh"),
    ]

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._client = InstrumentedClient()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="state-panel"):
                yield StatePanel(id="state")
            with Vertical(id="log-panel"):
                yield RichLog(
                    id="log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                )
        yield CommandInput(
            _COMMAND_SUGGESTIONS,
            placeholder="Enter command (type 'help' for list)",
            id="input-bar",
        )

    def on_mount(self) -> None:
        self.title = f"Lumagen — {self._host}:{self._port}"
        self.query_one("#state-panel").border_title = "State"
        self.query_one("#log-panel").border_title = "Protocol Log"

        self._client._on_line_sent.append(self._log_sent)
        self._client._on_line_received.append(self._log_received)

        self.query_one("#input-bar", Input).focus()
        self._connect_client()

    @work(exclusive=True)
    async def _connect_client(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[dim]Connecting…[/]")

        await self._client.connect(
            self._host,
            self._port,
            on_state_changed=self._on_state_changed,
            on_connection_changed=self._on_connection_changed,
        )

        if self._client.state.connected:
            log.write("[green]Connected.[/]")
            await self._client.fetch_full_state()
            self._refresh_state()
            log.write("[dim]Fetching labels…[/]")
            await self._client.get_labels()
            self._refresh_state()
            log.write(HELP_TEXT)
        else:
            log.write("[red]Connection failed.[/]")

    def _on_state_changed(self) -> None:
        self.call_later(self._refresh_state)

    def _on_connection_changed(self, connected: bool) -> None:
        def _update() -> None:
            log = self.query_one("#log", RichLog)
            if connected:
                log.write("[green]Connected.[/]")
            else:
                log.write("[red]Disconnected.[/]")
            self._refresh_state()

        self.call_later(_update)

    def _refresh_state(self) -> None:
        panel = self.query_one("#state", StatePanel)
        panel.update_state(self._client.state)

    def _log_sent(self, cmd: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.call_later(
            self.query_one("#log", RichLog).write,
            f"[dim]{ts}[/] [bold cyan]→[/] {cmd}",
        )

    def _log_received(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.call_later(
            self.query_one("#log", RichLog).write,
            f"[dim]{ts}[/] [bold green]←[/] {line}",
        )

    # -- Input handling ----------------------------------------------------

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return
        await self._dispatch_command(raw)

    async def _dispatch_command(self, raw: str) -> None:
        log = self.query_one("#log", RichLog)
        lower = raw.lower()
        parts = lower.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            await self._client.disconnect()
            self.exit()
            return

        if cmd in ("help", "?"):
            log.write(HELP_TEXT)
            return

        if cmd == "on":
            await self._client.power_on()
            return
        if cmd == "off":
            await self._client.power_off()
            return

        # Bare letter → memory bank shortcut
        if cmd in "abcd" and not arg:
            await self._client.select_memory(cmd)
            return

        # Bare number → input shortcut
        if cmd.isdigit() and not arg:
            num = int(cmd)
            if not 1 <= num <= 19:
                log.write(f"[red]Input number must be 1-19, got {num}[/]")
                return
            await self._client.select_input(num)
            return

        if cmd == "aspect" and arg:
            if arg in ASPECT_COMMANDS:
                await self._client.set_aspect(arg)
            else:
                names = ", ".join(sorted(ASPECT_COMMANDS.keys()))
                log.write(f"[red]Unknown aspect: {arg}[/]")
                log.write(f"[dim]  Valid: {names}[/]")
            return

        if cmd == "mode" and arg:
            try:
                val = int(arg)
            except ValueError:
                log.write(f"[red]Invalid mode: {arg} (use 1-8)[/]")
                return
            if not 1 <= val <= 8:
                log.write(f"[red]Mode must be 1-8, got {val}[/]")
                return
            await self._client.set_output_config(mode=val - 1)
            return

        if cmd == "cms" and arg:
            try:
                val = int(arg)
            except ValueError:
                log.write(f"[red]Invalid CMS: {arg} (use 1-8)[/]")
                return
            if not 1 <= val <= 8:
                log.write(f"[red]CMS must be 1-8, got {val}[/]")
                return
            await self._client.set_output_config(cms=val - 1)
            return

        if cmd == "style" and arg:
            try:
                val = int(arg)
            except ValueError:
                log.write(f"[red]Invalid style: {arg} (use 1-8)[/]")
                return
            if not 1 <= val <= 8:
                log.write(f"[red]Style must be 1-8, got {val}[/]")
                return
            await self._client.set_output_config(style=val - 1)
            return

        if cmd == "game":
            if arg in ("on", "1"):
                await self._client.set_game_mode(True)
            elif arg in ("off", "0"):
                await self._client.set_game_mode(False)
            else:
                log.write("[red]Usage: game on / game off[/]")
            return

        if cmd == "autoaspect":
            if arg in ("on", "1"):
                await self._client.set_auto_aspect(True)
            elif arg in ("off", "0"):
                await self._client.set_auto_aspect(False)
            else:
                log.write("[red]Usage: autoaspect on / autoaspect off[/]")
            return

        if cmd == "label" and arg:
            label_parts = arg.split(maxsplit=1)
            if len(label_parts) < 2 or len(label_parts[0]) < 2:
                log.write("[red]Usage: label <id> <text> (e.g. label A1 Apple TV)[/]")
                return
            label_id = label_parts[0].upper()
            category = label_id[0]
            try:
                user_idx = int(label_id[1:])
            except ValueError:
                log.write(f"[red]Invalid label id: {label_parts[0]}[/]")
                return
            # User-facing is 1-based, protocol is 0-based
            proto_idx = user_idx - 1
            if proto_idx < 0:
                log.write("[red]Label index must be >= 1[/]")
                return
            await self._client.set_label(category, proto_idx, label_parts[1])
            log.write(f"[green]Set label {label_id} = {label_parts[1]}[/]")
            return

        if cmd == "save":
            await self._client.save_config()
            log.write("[green]Config saved to flash[/]")
            return

        if cmd == "hotplug":
            if arg:
                try:
                    await self._client.trigger_hotplug(int(arg))
                except ValueError:
                    log.write(f"[red]Invalid input: {arg}[/]")
                    return
            else:
                await self._client.trigger_hotplug()
            log.write("[green]Hotplug triggered[/]")
            return

        if cmd == "remote" and arg:
            if arg in REMOTE_COMMANDS:
                await self._client.send_remote_command(arg)
            else:
                names = ", ".join(
                    k for k in sorted(REMOTE_COMMANDS.keys()) if not k.isdigit()
                )
                log.write(f"[red]Unknown remote command: {arg}[/]")
                log.write(f"[dim]  Valid: {names}[/]")
            return

        if cmd == "osd":
            rest = raw.split(maxsplit=1)
            if len(rest) < 2:
                await self._client.clear_message()
                return
            body = rest[1]
            # Optional leading digit sets duration (0-8=seconds, 9=persistent)
            if len(body) >= 2 and body[0].isdigit() and body[1] == " ":
                duration = int(body[0])
                body = body[2:]
            else:
                duration = 3
            # Allow \n for line breaks
            body = body.replace("\\n", "\n")
            await self._client.display_message(body, duration=duration)
            return

        if cmd == "labels" and not arg:
            self._show_labels(log)
            return

        if cmd == "refresh":
            if arg == "labels":
                log.write("[dim]Fetching labels…[/]")
                await self._client.get_labels()
                self._refresh_state()
                self._show_labels(log)
            else:
                await self._client.fetch_full_state()
                self._refresh_state()
            return

        # Raw RS232 commands start with Z
        if raw.startswith("Z"):
            await self._client.send_command(raw)
            return

        log.write(f"[red]Unknown command: {raw}[/]")
        log.write("[dim]Type 'help' for available commands.[/]")

    def _show_labels(self, log: RichLog) -> None:
        """Display cached labels in the log panel."""
        state = self._client.state
        label_sets: list[tuple[str, str, dict[str, str]]] = [
            ("Inputs (Mem A)", "A", state.input_labels),
            ("Inputs (Mem B)", "B", state.input_labels),
            ("Inputs (Mem C)", "C", state.input_labels),
            ("Inputs (Mem D)", "D", state.input_labels),
            ("Custom Modes", "1", state.custom_mode_labels),
            ("CMS", "2", state.cms_labels),
            ("Styles", "3", state.style_labels),
        ]
        for heading, prefix, labels in label_sets:
            group = {k: v for k, v in sorted(labels.items()) if k[0] == prefix}
            if group:
                log.write(f"[bold]{heading}:[/]")
                for lid, text in group.items():
                    display_id = f"{lid[0]}{int(lid[1:]) + 1}"
                    log.write(f"  {display_id}: {text}")

    # -- Actions -----------------------------------------------------------

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    async def action_refresh(self) -> None:
        await self._client.fetch_full_state()
        self._refresh_state()

    async def on_unmount(self) -> None:
        await self._client.disconnect()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lumagen Radiance Pro TUI",
    )
    parser.add_argument(
        "host",
        help="Hostname or IP of the Lumagen device",
    )
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=4999,
        help="TCP port (default: 4999)",
    )
    args = parser.parse_args()

    # Log all client protocol traffic to tui.log
    client_logger = logging.getLogger("client")
    handler = logging.FileHandler("tui.log")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    client_logger.addHandler(handler)
    client_logger.setLevel(logging.DEBUG)

    app = LumagenTUI(args.host, args.port)
    app.run()


if __name__ == "__main__":
    main()
