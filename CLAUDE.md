# CLAUDE.md

## Pre-flight
- Always verify `git status` is clean before making changes.

## Verification
- Use pre-commit hooks to verify work — do NOT run checkers (ruff, pyright, pytest, etc.) manually.
- Run: `pre-commit run --all-files`

## Python
- Always use `uv` to run Python, pytest, and tools (never bare `python` or `python3`).
- Always use `uv add` and `uv remove` to add or remove Python packages.

## Project overview
- Home Assistant custom integration for Lumagen Radiance Pro video processors.
- No external dependencies — self-contained async TCP client in `client.py`.
- Event-driven (no polling): coordinator sets `update_interval=None`, all state comes from the TCP stream.

## tui.py
- Runs via `#!/usr/bin/env -S uv run python` — uses the project venv, not `uv run --script`.
- PEP 723 inline script metadata does NOT apply; new deps go in `pyproject.toml` `[dependency-groups] dev`.

## Reference docs
- `docs/development.md` — development setup, pre-commit details
- `docs/architecture.md` — architecture, state management, startup sequence, connection lifecycle
- `docs/rs232_command_reference.md` — full Lumagen RS-232 command & query reference
