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

### Select

| Entity             | Description |
|--------------------|-------------|
| Input Source       | Select from labeled inputs (labels read from device on power-on) |
| Source Aspect Ratio | 4:3, Letterbox, 16:9, 1.85, 1.90, 2.00, 2.20, 2.35, 2.40, NLS |
| Memory Bank        | Recall memory A / B / C / D |

### Sensors

**Status** (available when device is active):

| Sensor               | Description |
|----------------------|-------------|
| Logical Input        | Current logical input number |
| Physical Input       | Current physical input |
| Output Resolution    | Output vertical resolution and refresh rate |
| Source Aspect Ratio  | Detected source content aspect |
| Source Dynamic Range | SDR / HDR |
| Input Configuration  | Active input config number |
| Output CMS           | Active color management system (0–7) |
| Output Style         | Active output style (0–7) |

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
- **Keepalive**: `ZQS00` sent every 30 s; if no `!S00,Ok` within 5 s,
  the client reconnects

On power-on (standby → active), the integration waits 5 seconds then
re-queries full device state and fetches all input labels.

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

Labels are fetched from the device on power-on. If you see default names:
1. Confirm you have custom labels configured on the Lumagen
2. Power-cycle the device (or toggle the power switch) to trigger a label fetch
3. Labels are per memory bank — switching banks shows that bank's labels

## License

Apache License 2.0
