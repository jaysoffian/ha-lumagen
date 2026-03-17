# CLAUDE.md

## Pre-flight
- Always verify `git status` is clean before making changes.

## Verification
- Use pre-commit hooks to verify work — do NOT run checkers (ruff, pyright, pytest, etc.) manually.
- Run: `pre-commit run --all-files`
- Note: `pre-commit` is a shell wrapper in PATH:
  ```sh
  #!/bin/sh
  exec uvx --isolated --with pre-commit-uv pre-commit "$@"
  ```

## Python
- Always use `uv` to run Python, pytest, and tools (never bare `python` or `python3`).

## Project overview
- Home Assistant custom integration for Lumagen Radiance Pro video processors.
- No external dependencies — self-contained async TCP client in `client.py`.
- Event-driven (no polling): coordinator sets `update_interval=None`, all state comes from the TCP stream.

## Repo layout
```
custom_components/ha_lumagen/
  client.py        — async TCP client, RS-232 protocol, state dataclass
  coordinator.py   — HA DataUpdateCoordinator (event-driven, no polling)
  entity.py        — shared base entity (device_info, availability)
  config_flow.py   — single-step IP/port config flow
  sensor.py        — status + diagnostic sensors
  select.py        — input, aspect ratio, memory selects
  switch.py        — power, auto aspect, game mode switches
  button.py        — reload config, reset auto aspect, show input aspect
  remote.py        — menu navigation commands
  const.py         — domain, defaults, errors
tui.py             — standalone Textual TUI for interactive testing
```

## tui.py
- Runs via `#!/usr/bin/env -S uv run python` — uses the project venv, not `uv run --script`.
- PEP 723 inline script metadata does NOT apply; new deps go in `pyproject.toml` `[dependency-groups] dev`.

## Reference docs
- `docs/rs232_command_reference.md` — full Lumagen RS-232 command & query reference
- `docs/state_management.md` — state tier design, startup sequence, connection lifecycle
