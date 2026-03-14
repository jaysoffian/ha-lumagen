# Lumagen Radiance Pro Integration for Home Assistant

Home Assistant custom integration for Lumagen Radiance Pro video processors.
Communicates directly over TCP via a serial-to-TCP adapter (e.g. Global Cache
IP2SL, USR-TCP232-302) connected to the Lumagen's RS-232 port.

No external libraries — the integration contains its own async TCP client that
speaks the Lumagen RS-232 protocol natively.

## Lumagen Setup

The Lumagen must be configured for the integration to work correctly.

**MENU → Other → I/O Setup → RS-232 Setup:**

| Setting              | Value     |
|----------------------|-----------|
| Echo                 | On        |
| Delimiters           | Off       |
| Report mode changes  | Full v4   |

**MENU → Other → OnOff Setup:**

| Setting     | Value    |
|-------------|----------|
| OnMessage   | Off      |
| OffMessage  | Off      |

Optional: enable extended aspect ratios (MENU → Input → Options → Aspect Setup
→ Aspect Opts → Extended) to detect/select 4:3 Pillarbox, 1.375 Pillarbox,
1.66 Pillarbox, 2.10, 2.55, and 2.76.

The serial-to-TCP adapter must match the Lumagen's RS-232 settings (default:
9600 bps, 8N1, no flow control).

## Installation

### HACS

1. Open HACS → Integrations
2. Three-dot menu → Custom repositories
3. Add this repository URL, category "Integration"
4. Install and restart Home Assistant

### Manual

Copy `custom_components/ha_lumagen` into your Home Assistant
`custom_components` directory and restart.

## Configuration

1. **Settings → Devices & Services → Add Integration → Lumagen**
2. Enter the IP address and port of your serial-to-TCP adapter (default port: 4999)
3. The integration tests the connection with an alive query before completing setup

## Entities

### Switch

| Entity | Description |
|--------|-------------|
| Power  | Turn device on / standby. Optimistic state for instant UI feedback. |

### Button

| Entity             | Description |
|--------------------|-------------|
| Refresh Config     | Re-fetch identity, game mode, and all labels from the device and save to disk. |
| Reset Auto Aspect  | Reset auto aspect detection (ZY550). |

### Select

| Entity             | Description |
|--------------------|-------------|
| Input              | Select from labeled inputs (cached on disk; press Refresh Config to update) |
| Input Aspect Ratio | Auto, 4:3, Letterbox, 16:9, 1.85, 1.90, 2.00, 2.10, 2.20, 2.35, 2.40, 2.55, 2.76, NLS |
| Memory             | Select input memory A / B / C / D |

### Sensors

**Status** (available when device is active):

| Sensor                       | Description |
|------------------------------|-------------|
| Logical Input                | Current logical input number |
| Physical Input               | Current physical input |
| Input Configuration          | Active input config number |
| Source Resolution             | Source vertical resolution |
| Source Refresh Rate           | Source vertical refresh rate |
| Source Content Aspect Ratio   | Detected source content aspect |
| Source Raster Aspect Ratio    | Source raster aspect |
| Source Dynamic Range          | SDR / HDR |
| Source Mode                   | Progressive / Interlaced |
| NLS Active                   | Non-linear stretch active |
| Detected Content Aspect Ratio | Auto-detected content aspect (v4 firmware) |
| Detected Raster Aspect Ratio  | Auto-detected raster aspect (v4 firmware) |
| Output Resolution             | Output vertical resolution |
| Output Refresh Rate           | Output vertical refresh rate |
| Output Aspect Ratio           | Output aspect ratio |
| Output Colorspace             | Output colorspace (e.g. BT.709, BT.2020) |
| Output CMS                    | Active color management system (0–7) |
| Output Style                  | Active output style (0–7) |

**Diagnostic** (available whenever connected, even in standby):

| Sensor            | Description |
|-------------------|-------------|
| Model Name        | e.g. "RadiancePro" |
| Software Revision | Firmware version |
| Model Number      | Hardware model number |
| Serial Number     | Device serial number |

### Remote

Send navigation and control commands to the Lumagen menu system.

Available commands: `up`, `down`, `left`, `right`, `menu`, `ok`, `enter`,
`exit`, `back`, `home`, `info`, `alt`, `clear`, `0`–`9`.

## Usage Examples

### Power

```yaml
service: switch.turn_on
target:
  entity_id: switch.lumagen_radiancepro_power
```

### Input Selection

```yaml
service: select.select_option
target:
  entity_id: select.lumagen_radiancepro_input_source
data:
  option: "HDMI 1"
```

### Aspect Ratio

```yaml
service: select.select_option
target:
  entity_id: select.lumagen_radiancepro_source_aspect_ratio
data:
  option: "2.35"
```

### Remote Commands

```yaml
service: remote.send_command
target:
  entity_id: remote.lumagen_radiancepro_remote
data:
  command:
    - menu
    - down
    - enter
```

### Automation Example

```yaml
automation:
  - alias: "Switch to Apple TV"
    trigger:
      - platform: state
        entity_id: media_player.apple_tv
        to: "playing"
    action:
      - service: select.select_option
        target:
          entity_id: select.lumagen_radiancepro_input_source
        data:
          option: "HDMI 2"
```

## Architecture

The integration has no external dependencies. Communication with the Lumagen is
handled by `client.py`, a self-contained async TCP client (~400 lines).

```
┌──────────────────────────────────────────────────┐
│                  LumagenClient                   │
│                                                  │
│  asyncio.open_connection(host, port)             │
│  ┌────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ _read_loop │  │ send_command│  │ _keepalive│  │
│  └─────┬──────┘  └─────────────┘  └──────────┘  │
│        │ parses lines, updates state             │
│        ▼                                         │
│  LumagenState (dataclass)                        │
│        │ calls on_state_changed callback         │
│        ▼                                         │
│  LumagenCoordinator.async_set_updated_data()     │
└──────────────────────────────────────────────────┘
```

### Event-Driven Updates

The coordinator sets `update_interval=None` — no polling. All state updates
come from the TCP stream:

- **Mode changes**: the Lumagen pushes `!I24,…` unsolicited
- **Power changes**: `Power-up complete.` / `POWER OFF.` sentinels
- **Input changes**: detected from ZQI00/ZQI24, triggers ZQI18 fetch for
  per-input output config
- **Keepalive**: `ZQI00` sent after 30 s of idle; any received data resets
  the timer

Device state is split into three tiers — config (stored on disk), per-input
runtime, and signal (unsolicited). See
[docs/state_management.md](docs/state_management.md) for details on what is
fetched when and why.

For the full RS-232 command and query reference, see
[docs/rs232_command_reference.md](docs/rs232_command_reference.md).

## Troubleshooting

### Connection fails during setup

- Verify the serial-to-TCP adapter is reachable at the configured IP/port
- Confirm the adapter's serial settings match the Lumagen (9600 8N1)
- Check that the Lumagen is powered on (the alive query needs a response)

### Entities show unavailable

- Status sensors require the device to be active (not in standby)
- Diagnostic sensors only require a TCP connection
- Check Home Assistant logs for keepalive timeouts or reconnect messages

### Input source dropdown shows "Input 1", "Input 2", …

Labels are cached on disk. If you see default names:
1. Confirm you have custom labels configured on the Lumagen
2. Press the **Refresh config** button entity to fetch labels from the device
3. Labels are per input memory — switching memories shows that memory's labels

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
# Set up the dev environment
uv sync

# Run tests
uv run pytest tests/ -v

# Lint + format
uv run ruff check custom_components/ tests/
uv run ruff format custom_components/ tests/

# Type check
uv run ty check

# Run all checks (ruff, ty, pytest, trailing whitespace, etc.)
uv run pre-commit run --all-files

# Install pre-commit as a git hook
uv run pre-commit install
```

### TUI

A standalone Textual TUI for exercising the client against a real Lumagen:

```bash
./tui.py <host> [port]
```

Split-pane interface with live device state on the left, protocol log on the
right, and a command input at the bottom. Type `help` for available commands
(raw RS-232, power, input, memory, aspect, remote, OSD, labels, etc.).

### Repo layout

```
custom_components/ha_lumagen/
  client.py        — async TCP client, RS-232 protocol, state dataclass
  coordinator.py   — HA DataUpdateCoordinator (event-driven, no polling)
  entity.py        — shared base entity (device_info, availability)
  config_flow.py   — single-step IP/port config flow
  sensor.py        — status + diagnostic sensors
  select.py        — input, aspect ratio, memory
  switch.py        — power on/off
  button.py        — refresh config, reset auto aspect buttons
  remote.py        — menu navigation commands
  const.py         — domain, defaults, errors
tui.py             — standalone Textual TUI for interactive testing
docs/
  rs232_command_reference.md — full Lumagen RS-232 command + query reference
  state_management.md        — state tier design, startup sequence, connection lifecycle
tests/
  test_client.py   — response parsing and protocol tests
```

## License

Apache License 2.0
