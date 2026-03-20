# Lumagen Radiance Pro Integration for Home Assistant

This [integration](https://www.home-assistant.io/getting-started/concepts-terminology/#integrations) connects your [Lumagen Radiance Pro](https://www.lumagen.com/products-sales/p/explore-radiance-pro) video processor to your [Home Assistant](https://www.home-assistant.io) installation.

## TCP/IP to Serial Adapter Setup

Required: A TCP/IP to Serial adapter such as the [Global Cache iTach IP2SL](https://www.amazon.com/Global-Cache-iTach-Serial-IP2SL/dp/B0051BU1X4) or [USR-TCP232-302](https://www.amazon.com/USR-TCP232-302-Serial-Ethernet-Converter-Support/dp/B01GPGPEBM)\* connected to the Lumagen's RS-232 port.

Connect the adapter to the Lumagen's RS-232 DB-9 male DTE port using the appropriate cable:

- The IP2SL has a DB-9 male DTE port. Connect it using a [DB-9 female-to-female null-modem cable](https://www.startech.com/en-us/cables/scnm9ff1mbk).
- The USR-TCP232-302 has a DB-9 female DCE port. Connect it using a [DB-9 male-to-female straight-through cable](https://www.startech.com/en-us/cables/mxt1001mbk).

The adapter's serial port settings must match the Lumagen's RS-232 port settings (default: 9600 bps, 8N1, no flow control).

Connect the adapter to your local network. You'll need the adapter's IP address and port (default 4999) when configuring the integration later.

\* *This integration is developed and tested against the USR-TCP232-302.*

## Lumagen Setup

The Lumagen should be configured as follows for the integration to work correctly.

1. **MENU → Other → I/O Setup → RS-232 Setup:**
   - **Echo-RS232**: On (Lumagen recommends "On". If set to "Off" it may affect the ability to do software updates. *This integration should work either way, but is tested with it On.*)
   - **Echo-USB**: On (Lumagen recommends "On". If set to "Off" it may affect the ability to do software updates. *Mentioned only for completeness as the TCP/IP to serial adapter connects to the RS-232 port.*)
   - **Delimiters**: Off (Lumagen recommends "Off". This works reliably and is easier to implement.  *This integration WILL NOT work unless Delimiters=Off.*)
   - **Report mode changes**: Full v5 (Optional but recommended. *Enables the integration to receive real-time updates from the Lumagen.*)
2. **MENU → Other → OnOff Setup:**
    - **On Message**: N (Message may interfere with integration.)
    - **Off Message**: N (Message may interfere with integration.)
3. **MENU → Input → Options → Aspect Setup:**
   - **Aspect Opts**: Extended (Optional but recommended. Enables detection/selection of 4:3 Pillarbox, 1.375 Pillarbox, 1.66 Pillarbox, 2.10, 2.55, and 2.76 aspect ratios.)

## Installation

### HACS

1. Install [HACS](https://hacs.xyz)
2. Open HACS → Integrations
3. Open triple-dot menu ( ⠇) → Custom repositories
4. Add this repository's URL (`https://github.com/jaysoffian/ha_lumagen`), category "Integration"
5. Install this integration and restart Home Assistant


### Manual

Copy `custom_components/ha_lumagen` into your Home Assistant `custom_components` directory and restart.

## Configuration

1. Settings → Devices & Services → Add Integration → Lumagen
2. Enter the hostname (or IP address) and port (default: 4999) of your TCP/IP to Serial Adapter.

The integration tests the connection before completing setup. Configuration information that rarely changes (identity, firmware revision, game mode, and labels) are loaded from your Lumagen at this time and then cached across HA restarts. Use the **Reload config** button to refresh this information in the future.

After setup, go to **Settings → Devices & Services → Lumagen → Configure** to choose which aspect ratios appear in the Aspect Ratio select menu.

## Entities

### Switches

- **Power** — Turn device on / standby.
- **Auto Aspect** — Enable / disable auto aspect detection.
- **NLS** — Toggle non-linear stretch (see [NLS](#nls-non-linear-stretch) below).

### Buttons

- **Show input aspect** — Show input and aspect info on the Lumagen OSD.
- **Restart outputs** — Restart outputs if your TV/projector has trouble locking on the signal.
- **Reload config** — Reload rarely changing configuration information (identity, firmware revision, game mode, and labels) from your Lumagen.

### Selects

- **Input** — Select input.
- **Aspect Ratio** — Auto, Letterbox, 1.33, 1.78, 1.85, 1.90, 2.00, 2.10, 2.20, 2.35, 2.40, 2.55, 2.76. [Configurable](#configuring-the-aspect-ratio-menu).
- **Memory** — Select input memory A / B / C / D.

### Sensors

All sensors require the device to be active (not in standby).

- **Logical Input** — Current logical input number
- **Physical Input** — Current physical input
- **Input Configuration** — Active input config number
- **Input Video Status** — No Source / Active Video / Test Pattern
- **Source Resolution** — Source vertical resolution
- **Source Refresh Rate** — Source vertical refresh rate
- **Source Content Aspect Ratio** — Detected source content aspect
- **Source Raster Aspect Ratio** — Source raster aspect
- **Source Dynamic Range** — SDR / HDR
- **Source Mode** — Progressive / Interlaced
- **Source 3D Mode** — Off / Frame Sequential / Frame Packed / Top-Bottom / Side-by-Side
- **NLS Active** — Non-linear stretch active
- **Detected Content Aspect Ratio** — Auto-detected content aspect
- **Detected Raster Aspect Ratio** — Auto-detected raster aspect
- **Output Resolution** — Output vertical resolution
- **Output Refresh Rate** — Output vertical refresh rate
- **Output Aspect Ratio** — Output aspect ratio
- **Output Mode** — Progressive / Interlaced
- **Output Colorspace** — Output colorspace (e.g. BT.709, BT.2020)
- **Output 3D Mode** — Off / Frame Sequential / Frame Packed / Top-Bottom / Side-by-Side
- **Active Outputs** — Which outputs are active (1–4)
- **Output CMS** — Active color management system (0–7)
- **Output CMS Label** — Label for the active CMS
- **Output Style** — Active output style (0–7)
- **Output Style Label** — Label for the active output style
- **Input Label** — Label for the current input

Device identity (model, serial, firmware) is shown in HA's device info rather than as separate entities.

### Remote

Send navigation and control commands to the Lumagen menu system.

Available commands: `up`, `down`, `left`, `right`, `menu`, `ok`, `enter`,
`exit`, `back`, `home`, `info`, `alt`, `clear`, `help`, `previous`, `pip_off`,
`pip_select`, `pip_swap`, `pip_mode`, `save`, `zone`, `hdr_setup`,
`test_pattern`, `osd_on`, `osd_off`, `10+`, `0`–`9`.

## Aspect Ratio and Auto Aspect

The Aspect Ratio select and Auto Aspect switch are kept in sync:

| Action              | Auto Aspect | Aspect              |
|---------------------|-------------|---------------------|
| Select "Auto"       | On          | (device-detected)   |
| Select a ratio      | Off         | Set to selection    |

### Configuring the Aspect Ratio Menu

By default all supported aspect ratios appear in the select menu. To show only the ratios you use, go to **Settings → Devices & Services → Lumagen → Configure** and select which ratios to include.

### NLS (Non-Linear Stretch)

NLS stretches a narrower aspect to fill a wider display non-linearly (more stretch at the edges, less in the center). NLS is exposed as a dedicated **switch** entity that can be toggled independently of the aspect ratio selection.

## Usage Examples

### Power

```yaml
action: switch.turn_on
target:
  entity_id: switch.lumagen_radiancepro_power
```

### Input Selection

```yaml
action: select.select_option
target:
  entity_id: select.lumagen_radiancepro_input
data:
  option: "HDMI 1"
```

### Aspect Ratio

```yaml
action: select.select_option
target:
  entity_id: select.lumagen_radiancepro_aspect_ratio
data:
  option: "2.35"
```

### Remote Commands

```yaml
action: remote.send_command
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

- `ha_lumagen.show_osd_message`: Show an OSD message
- `ha_lumagen.show_osd_volume_bar`: Show a volume bar
- `ha_lumagen.clear_osd_message`: Clear any OSD message

Example:

```yaml
action: ha_lumagen.show_osd_message
data:
  line_one: "Hello" # Maximum 30 characters (ASCII 0x20 - 0x7a)
  line_two: "World" # Optional second line
  duration: 5 # Clear in 5 secs. Max is 9. Default is 3. Use 0 to disable clearing.
  block_char: "X" # Optional character to render as █ if it appears in message.

# Show a volume bar on the Lumagen's OSD like so:
# |63.5% ███████████████████     |
action: ha_lumagen.show_osd_volume_bar
data:
  level: 0.635
```

### Automation Examples

**Settings → Automations & scenes → +Create automation → Create new automation → triple-dot menu (⠇) → Edit in YAML**

#### Switch input on playback

```yaml
alias: "Switch to Apple TV"
trigger:
  - platform: state
    entity_id: media_player.apple_tv
    to: "playing"
action:
  - action: select.select_option
    target:
      entity_id: select.lumagen_radiancepro_input
    data:
      option: "HDMI 2"
```

### Lumagen OSD

##### AVR Volume

This example uses the Lumagen OSD to show volume changes from a Denon/Marantz AVR connected with the [built-in HA integration](https://www.home-assistant.io/integrations/denonavr/).

The volume is displayed on a single line within the Lumagen's 30 character-wide OSD like so: `63.5% ███████████████         `

```yaml
alias: "Show AVR volume on Lumagen"
triggers:
  - trigger: state
    entity_id: media_player.denon_avr_x3800h  # adjust to your entity
    attribute: volume_level
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.volume_level is not none }}"
actions:
  - action: ha_lumagen.show_osd_volume_bar
    data:
      level: "{{ trigger.to_state.attributes.volume_level }}"
mode: single
```

##### AVR  Volume (scaled)

If you limited your AVR's maximum volume (e.g. 80), the bar will never fill completely. This example scales the bar so that volume level 0.8 is a full bar: `80.0% ████████████████████████`

```yaml
alias: "Show AVR volume on Lumagen (scaled)"
triggers:
  - trigger: state
    entity_id: media_player.denon_avr_x3800h
    attribute: volume_level
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.volume_level is not none }}"
actions:
  - action: ha_lumagen.show_osd_volume_bar
    data:
      level: "{{ trigger.to_state.attributes.volume_level / 0.8 }}"
      label: >-
        {% if trigger.to_state.attributes.volume_level == 0 %}
          Min
        {% elif trigger.to_state.attributes.volume_level >= 0.8 %}
          Max
        {% else %}
          {{ (trigger.to_state.attributes.volume_level * 100) | round(1) }}
        {% endif %}
mode: single
```

##### AVR Volume (decibels)

Denon / Marantz AVRs can display their volume in in two scales:

1. **0 – 98**: Default. 80 is reference volume.
2. **79.5 dB — 18.0 dB**: 0 dB is reference volume.

This example shows how to mimic the decibel scale.

```yaml
alias: "Show AVR volume on Lumagen (dB)"
triggers:
  - trigger: state
    entity_id: media_player.denon_avr_x3800h
    attribute: volume_level
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.volume_level is not none }}"
actions:
  - action: ha_lumagen.show_osd_volume_bar
    data:
      level: "{{ trigger.to_state.attributes.volume_level }}"
      label: >-
        {% if trigger.to_state.attributes.volume_level == 0 %}
          Min
        {% elif trigger.to_state.attributes.volume_level == 1 %}
          Max
        {% else %}
          {{ (trigger.to_state.attributes.volume_level * 100 - 80) | round(1) }}
        {% endif %}
mode: single
```

##### AVR Mute Status

This example displays "Mute" as long as the AVR is muted.

```yaml
alias: "Show mute on Lumagen"
triggers:
  - trigger: state
    entity_id: media_player.denon_avr_x3800h  # adjust to your entity
    attribute: is_volume_muted
actions:
  - if: "{{ trigger.to_state.attributes.is_volume_muted }}"
    then:
      - action: ha_lumagen.show_osd_message
        data:
          line_one: "Mute"
          duration: 0
    else:
      - action: ha_lumagen.clear_osd_message
mode: single
```

## Troubleshooting

### Connection fails during setup

- Verify the TCP/IP-to-serial adapter is reachable at the configured IP/port
- Confirm the adapter's serial settings match the Lumagen's (9600 8N1)
- Try with the Lumagen powered on. It may not respond if its standby power is configured to "Lowest".

### Entities show unavailable

- Sensors require the device to be active (not in standby)
- Power switch and Reload Config are available whenever connected
- Check Home Assistant logs for keepalive timeouts or reconnect messages

### Input source dropdown shows "Input 1", "Input 2", …

1. Confirm you have custom labels configured on your Lumagen
2. Press the **Reload config** button entity to fetch labels from your Lumagen
3. Labels are per input memory — switching memories shows that memory's labels

### TUI

A standalone Textual TUI for exercising the client against a real Lumagen:

```bash
./tui.py <host> [port]
# or via env vars:
LUMAGEN_HOST=lrp LUMAGEN_PORT=5555 ./tui.py
```

<img src="tui.svg" alt="TUI screenshot" width="600">

## License

Apache License 2.0
