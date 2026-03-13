#!/usr/bin/env -S uv run python
"""Textual TUI for exercising the Lumagen Radiance Pro TCP client."""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import BindingType
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


def _cms_style(s: LumagenState) -> str:
    if s.output_cms is None:
        return "—"
    cms = s.cms_labels.get(f"2{s.output_cms}", str(s.output_cms))
    style = s.style_labels.get(f"3{s.output_style}", str(s.output_style))
    return f"{cms} / {style}"


_STATE_FIELDS: list[tuple[str, str, Callable[[LumagenState], str | None] | None]] = [
    ("Connected", "connected", lambda s: "Yes" if s.connected else "No"),
    (
        "Power",
        "device_status",
        lambda s: {"Active": "On", "Standby": "Off"}.get(s.device_status or "", "—"),
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
    ("CMS / Style", "_cms_style", _cms_style),
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
[bold]Commands:[/]
  on / off               (turn Lumagen on or off)
  <1-19>                 (select input)
  a / b / c / d          (select memory bank)
  aspect <name>          (4:3, 16:9, 2.40, NLS, …)
  remote <cmd>           (menu, up, down, ok, exit, …)
  osd <text>             (display OSD message)
  labels                 (fetch all input labels)
  refresh                (re-query full state)
  help                   (show this message)
  quit / exit / q        (exit)

[bold]Raw RS232:[/]
  Z...                   (e.g. ZQS01, ZQI24, ZY530MCS)

[bold]Keyboard shortcuts:[/]
  Ctrl+Q                 quit
  Ctrl+L                 clear protocol log
  Ctrl+R                 refresh state
"""


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
        yield Input(
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
            text = raw.split(maxsplit=1)
            if len(text) > 1:
                await self._client.display_message(text[1])
            else:
                await self._client.clear_message()
            return

        if cmd == "labels":
            log.write("[dim]Fetching labels…[/]")
            labels = await self._client.get_labels()
            for heading, prefix in (
                ("Inputs", "ABCD"),
                ("Custom Modes", "1"),
                ("CMS", "2"),
                ("Styles", "3"),
            ):
                group = {k: v for k, v in sorted(labels.items()) if k[0] in prefix}
                if group:
                    log.write(f"[bold]{heading}:[/]")
                    for lid, text in group.items():
                        log.write(f"  {lid}: {text}")
            self._refresh_state()
            return

        if cmd == "refresh":
            await self._client.fetch_full_state()
            self._refresh_state()
            return

        # Raw RS232 commands start with Z
        if raw.startswith("Z"):
            await self._client.send_command(raw)
            return

        log.write(f"[red]Unknown command: {raw}[/]")
        log.write("[dim]Type 'help' for available commands.[/]")

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

    app = LumagenTUI(args.host, args.port)
    app.run()


if __name__ == "__main__":
    main()
