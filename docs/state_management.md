# State Management Design

The HA integration categorizes Lumagen device state into two tiers based
on how often each piece of data changes, which determines when and how it
is fetched.

## 1. Config state (stored on disk, fetched on demand)

Data that is configured once on the Lumagen and rarely changes. Persisted
to HA storage (`ha_lumagen.<entry_id>.info`) so it survives HA restarts
without querying the device.

| Data             | Command | Notes                                      |
|------------------|---------|----------------------------------------------|
| Model / serial   | ZQS01   | Only changes on hardware swap                |
| Firmware version | ZQS01   | Changes after firmware update                 |
| Game mode        | ZQI53   | Per-input config in Input > Options > A/V Delay |
| Auto aspect      | ZQI54   | Per-input config (fw ≥041824)                  |
| Input labels     | ZQS1*   | 40 labels (A0-D9), set via Lumagen menus      |
| Mode/CMS/Style labels | ZQS1* | 24 labels (custom mode, CMS, style)       |

Model, serial, firmware, and labels are shown in the UI but not exposed
as separate entities — identity fields live in HA's device info, and
labels populate the Input select dropdown.

Game mode is queried and stored but not exposed as an entity. It's a
per-input setting saved on the Lumagen; switching inputs already applies
the right value. The TUI `game on/off` command is available for testing.

**When fetched:**
- First-ever setup (no stored data) — automatic with backoff retry.
- User presses the "Reload config" button entity.

**Why not on every startup:** Labels alone require 64 sequential queries
with 2-second timeouts each. The device can be slow to respond after
boot, causing timeouts and retries. Since these values almost never
change, caching them avoids unnecessary device traffic and startup delays.

## 2. Signal state (unsolicited + keepalive)

Volatile state that changes as the source signal changes or the user
switches inputs/memory. The Lumagen reports most of this automatically
when configured with "Report mode changes: Full v5" (unsolicited ZQI25).

| Data                        | Source       |
|-----------------------------|--------------|
| Power on/off                | Unsolicited sentinels (`Power-up complete.` / `POWER OFF.`), ZQI25 v5 field PWR |
| Input selection             | ZQI25 unsolicited (v3+ fields II/KK) |
| Input memory (A/B/C/D)      | ZQI25 unsolicited (v5 field MEM) |
| Input configuration         | ZQI25 unsolicited |
| Input video status          | ZQI25 unsolicited (field 0: No Source/Active Video/Test Pattern) |
| Source resolution/rate      | ZQI25 unsolicited |
| Source aspect (raster/content/detected) | ZQI25 unsolicited |
| Source dynamic range (SDR/HDR) | ZQI25 unsolicited |
| Source mode (progressive/interlaced) | ZQI25 unsolicited |
| Source 3D mode              | ZQI25 unsolicited (field 3) |
| NLS status                  | ZQI25 unsolicited (field 7: `N` = active, `-` = off) |
| Output resolution/rate/aspect | ZQI25 unsolicited |
| Output mode (progressive/interlaced) | ZQI25 unsolicited (v2+ field 18) |
| Output colorspace           | ZQI25 unsolicited |
| Output 3D mode              | ZQI25 unsolicited (field 8) |
| Active outputs (bitmask)    | ZQI25 unsolicited (field 9, WWWW hex) |
| Output CMS                  | ZQI25 unsolicited |
| Output Style                | ZQI25 unsolicited |

**Keepalive:** When the connection has been idle for 30 seconds (no data
received at all), a probe is sent. The probe depends on power state:
- **Device on:** ZQI25 — full signal state including input memory
- **Device off:** ZQS02 — power status check

Any received data — including unsolicited ZQI25 reports — resets the idle
timer. This means during active use (source changes, input switches), no
keepalive traffic is generated; the device's own reports prove liveness.

## 3. Optimistic vs authoritative state

Some controls set optimistic state for instant UI feedback, then let the
next device response confirm or correct it.

**Optimistic (single-command, reliable):**
- Power on/off, input selection, input memory, auto aspect toggle
- Aspect ratio selection (non-NLS): set immediately, confirmed by I54 + I25 queries

**Authoritative only (multi-command or unreliable):**
- NLS variants (4:3 NLS, 16:9 NLS, 1.85 NLS): send the base aspect
  command followed by `N`, then query I54 + I25 for the final state. No
  optimistic state is set because the device fires an intermediate I24
  response after the base aspect command (before processing `N`) that
  would overwrite it.
- Reset auto aspect (ZY550): queries I54 + I25 afterward to get the
  device's actual state.

### NLS caveats

NLS (Non-Linear Stretch) on the Lumagen remote is a two-button sequence:
press an aspect ratio (4:3, 16:9, or 1.85) then press NLS. The
integration replicates this by sending both commands.

Known device-level issues:
- **1.85 NLS is unreliable**: works roughly 50% of the time with a 16:9
  source. The device sets the aspect to 1.85 but sometimes does not
  engage NLS. This is a firmware limitation, not an integration bug.
- **4:3 NLS and 16:9 NLS are reliable** in testing.
- Selecting any aspect ratio (including NLS variants) disables auto
  aspect. Selecting "Auto" re-enables it.
- "Reset auto aspect" clears NLS and re-enables auto aspect detection.

### Aspect / auto aspect interaction

| Action              | Auto aspect | NLS    | Aspect              |
|---------------------|-------------|--------|---------------------|
| Select "Auto"       | On          | Off    | (device-detected)   |
| Select a ratio      | Off         | Off    | Set to selection    |
| Select NLS variant  | Off         | On*    | Set to base ratio   |
| Reset auto aspect   | On          | Off    | (device-detected)   |
| Toggle auto aspect  | Toggled     | —      | —                   |

*NLS engagement depends on device firmware; 1.85 NLS is unreliable.

## Startup sequence

1. Connect to device, wait for TCP session (response-driven `wait_for`,
   5 s timeout).
2. Load config state from HA storage (identity, game mode, auto aspect,
   labels).
3. If no stored data, fetch identity (ZQS01).
4. Query power (ZQS02) — always needed, it's volatile.
5. Query config toggles (ZQI53 game mode, ZQI54 auto aspect).
6. If power is on, fetch runtime state (ZQI25).
7. If no stored config exists (first setup), fetch identity and all
   labels (blocking, before entity platform setup).

On power-on (off → on transition detected from ZQS02 poll response or
`Power-up complete.` sentinel):

1. Wait 10 seconds for the device to finish initialization.
2. Send ZQI25 to get full signal state.

Note: `None` to `on` transitions (initial state discovery after HA
restart or reconnect) do NOT trigger the power-on handler — the startup
sequence already handles this case.

## Connection lifecycle

- **Keepalive timeout:** If the probe gets no response within 5 seconds
  (and no other data arrives), the connection is considered dead and a
  reconnect is initiated.
- **Reconnect:** Exponential backoff (1s, 2s, 4s, ... up to 30s). On
  reconnect, power is re-fetched; if on, the keepalive handles ZQI25.
  Power state is NOT reset to None on disconnect, avoiding spurious
  power-on detection.
- **Idle tracking:** Uses `time.monotonic()` timestamp updated on every
  received line, not per-response events. This prevents false keepalive
  timeouts when the device is slow to respond (e.g., after boot).
