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
| Report mode changes  | Full v5   |

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

### Switches

| Entity       | Description |
|--------------|-------------|
| Power        | Turn device on / standby. Available even in standby. |
| Auto Aspect  | Enable / disable auto aspect detection. Syncs with aspect ratio selection (see below). |

### Buttons

| Entity             | Category      | Description |
|--------------------|---------------|-------------|
| Reset auto aspect  | Main controls | Reset auto aspect detection and re-enable it (ZY550). Also clears NLS. |
| Show input aspect  | Main controls | Pop up input and aspect info on the Lumagen OSD. |
| Reload config      | Configuration | Re-fetch identity and all labels from the device and save to disk. |

### Selects

| Entity       | Description |
|--------------|-------------|
| Input        | Select from labeled inputs. Labels are cached on disk; press Reload Config to update. |
| Aspect Ratio | Auto, 4:3, Letterbox, 16:9, 1.85–2.76, plus NLS variants (see below). |
| Memory       | Select input memory A / B / C / D. |

### Sensors

All sensors require the device to be active (not in standby).

| Sensor                       | Description |
|------------------------------|-------------|
| Logical Input                | Current logical input number |
| Physical Input               | Current physical input |
| Input Configuration          | Active input config number |
| Input Video Status           | No Source / Active Video / Test Pattern |
| Source Resolution             | Source vertical resolution |
| Source Refresh Rate           | Source vertical refresh rate |
| Source Content Aspect Ratio   | Detected source content aspect |
| Source Raster Aspect Ratio    | Source raster aspect |
| Source Dynamic Range          | SDR / HDR |
| Source Mode                   | Progressive / Interlaced |
| Source 3D Mode                | Off / Frame Sequential / Frame Packed / Top-Bottom / Side-by-Side |
| NLS Active                   | Non-linear stretch active |
| Detected Content Aspect Ratio | Auto-detected content aspect (v4+ firmware) |
| Detected Raster Aspect Ratio  | Auto-detected raster aspect (v4+ firmware) |
| Output Resolution             | Output vertical resolution |
| Output Refresh Rate           | Output vertical refresh rate |
| Output Aspect Ratio           | Output aspect ratio |
| Output Mode                   | Progressive / Interlaced |
| Output Colorspace             | Output colorspace (e.g. BT.709, BT.2020) |
| Output 3D Mode                | Off / Frame Sequential / Frame Packed / Top-Bottom / Side-by-Side |
| Active Outputs                | Which outputs are active (1–4) |
| Output CMS                    | Active color management system (0–7) |
| Output Style                  | Active output style (0–7) |

Device identity (model, serial, firmware) is shown in HA's device info
rather than as separate entities.

### Remote

Send navigation and control commands to the Lumagen menu system.

Available commands: `up`, `down`, `left`, `right`, `menu`, `ok`, `enter`,
`exit`, `back`, `home`, `info`, `alt`, `clear`, `previous`, `pip_off`,
`pip_select`, `pip_swap`, `pip_mode`, `save`, `hdr_setup`, `test_pattern`,
`osd_on`, `osd_off`, `0`–`9`.

## Aspect Ratio and Auto Aspect

The Aspect Ratio select and Auto Aspect switch are kept in sync:

| Action              | Auto Aspect | NLS    | Aspect              |
|---------------------|-------------|--------|---------------------|
| Select "Auto"       | On          | Off    | (device-detected)   |
| Select a ratio      | Off         | Off    | Set to selection    |
| Select NLS variant  | Off         | On*    | Set to base ratio   |
| Reset Auto Aspect   | On          | Off    | (device-detected)   |

### NLS (Non-Linear Stretch)

NLS stretches a narrower aspect to fill a wider display non-linearly
(more stretch at the edges, less in the center). The integration offers
three NLS variants:

- **4:3 NLS** — stretch 4:3 to 16:9
- **16:9 NLS** — stretch 16:9 to 2.35/2.40
- **1.85 NLS** — stretch 1.85 to 2.35/2.40

On the Lumagen remote, NLS is a two-button sequence (e.g. press 16:9 then
NLS). The integration sends both commands automatically.

**Caveat:** NLS behavior can be unreliable at the firmware level. In
testing, 4:3 NLS and 16:9 NLS work consistently, but **1.85 NLS works
roughly 50% of the time** — the device sometimes sets the aspect to 1.85
without engaging NLS. This is a firmware limitation. The integration
queries the device for authoritative state after sending NLS commands, so
the UI will always show what the device actually did.

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
  entity_id: select.lumagen_radiancepro_input
data:
  option: "HDMI 1"
```

### Aspect Ratio

```yaml
service: select.select_option
target:
  entity_id: select.lumagen_radiancepro_aspect_ratio
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

### Services

The integration registers domain-level services for OSD control:

| Service                      | Description |
|------------------------------|-------------|
| `ha_lumagen.display_message` | Show an OSD message (up to 60 chars, two 30-char lines). Set `block_char: true` to render `X` as █. |
| `ha_lumagen.display_volume`  | Show a volume bar (0-100) for 1 second, scaled for a 0-80 useful range. |
| `ha_lumagen.clear_message`   | Clear any OSD message. |

```yaml
# Show a custom message for 5 seconds
service: ha_lumagen.display_message
data:
  message: "Hello World"
  duration: 5

# Show a volume bar
service: ha_lumagen.display_volume
data:
  volume: 63.5
```

### Automation Examples

#### Switch input on playback

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
          entity_id: select.lumagen_radiancepro_input
        data:
          option: "HDMI 2"
```

#### Show Denon AVR volume on the Lumagen OSD

If you use a Denon/Marantz AVR with the
[built-in HA integration](https://www.home-assistant.io/integrations/denonavr/),
you can mirror volume changes on the Lumagen display — no separate daemon
needed:

```yaml
automation:
  - alias: "Show Denon volume on Lumagen"
    trigger:
      - platform: state
        entity_id: media_player.denon_avr  # adjust to your entity
        attribute: volume_level
    action:
      - service: ha_lumagen.display_volume
        data:
          # HA volume_level is 0.0-1.0; scale to 0-100
          volume: "{{ state_attr('media_player.denon_avr', 'volume_level') * 100 }}"
```

## Architecture

The integration has no external dependencies. Communication with the Lumagen is
handled by `client.py`, a self-contained async TCP client.

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

- **Mode changes**: the Lumagen pushes `!I25,…` unsolicited (Full v5)
- **Power changes**: `Power-up complete.` / `POWER OFF.` sentinels
- **Input/memory changes**: included in ZQI25 response
- **Keepalive**: `ZQI25` sent after 30 s of idle; any received data resets
  the timer

Device state is split into config (stored on disk) and signal (unsolicited).
See [docs/state_management.md](docs/state_management.md) for the full design
including startup sequence, optimistic vs authoritative state, NLS caveats,
and connection lifecycle.

For the full RS-232 command and query reference, see
[docs/rs232_command_reference.md](docs/rs232_command_reference.md).

## Troubleshooting

### Connection fails during setup

- Verify the serial-to-TCP adapter is reachable at the configured IP/port
- Confirm the adapter's serial settings match the Lumagen (9600 8N1)
- Check that the Lumagen is powered on (the alive query needs a response)

### Entities show unavailable

- Sensors require the device to be active (not in standby)
- Power switch and Reload Config are available whenever connected
- Check Home Assistant logs for keepalive timeouts or reconnect messages

### Input source dropdown shows "Input 1", "Input 2", …

Labels are cached on disk. If you see default names:
1. Confirm you have custom labels configured on the Lumagen
2. Press the **Reload config** button entity to fetch labels from the device
3. Labels are per input memory — switching memories shows that memory's labels

### NLS aspect shows unexpected result

NLS can be unreliable at the firmware level (see [NLS caveats](#nls-non-linear-stretch)
above). The integration always queries the device for authoritative state
after NLS commands, so the UI reflects what the device actually did.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
# Set up the dev environment
uv sync

# Run all checks (ruff, pyright, pytest, trailing whitespace, etc.)
pre-commit run --all-files
```

### TUI

A standalone Textual TUI for exercising the client against a real Lumagen:

```bash
./tui.py <host> [port]
# or via env vars:
LUMAGEN_HOST=192.168.1.100 ./tui.py
```

Split-pane interface with live device state on the left, protocol log on the
right, and a command input at the bottom. Type `help` for available commands
(raw RS-232, power, input, memory, aspect, remote, OSD, labels, fan, subtitle
shift, etc.).

### Repo layout

```
custom_components/ha_lumagen/
  client.py        — async TCP client, RS-232 protocol, state dataclass
  coordinator.py   — HA DataUpdateCoordinator (event-driven, no polling)
  entity.py        — shared base entity (device_info, availability)
  config_flow.py   — single-step IP/port config flow
  sensor.py        — signal status sensors
  select.py        — input, aspect ratio, memory selects
  switch.py        — power, auto aspect switches
  button.py        — reload config, reset auto aspect, show input aspect
  remote.py        — menu navigation commands
  const.py         — domain, defaults, errors
  services.yaml    — HA service descriptions for OSD services
tui.py             — standalone Textual TUI for interactive testing
docs/
  rs232_command_reference.md — full Lumagen RS-232 command + query reference
  state_management.md        — state tier design, startup sequence, connection lifecycle
tests/
  test_client.py   — response parsing and protocol tests
```
