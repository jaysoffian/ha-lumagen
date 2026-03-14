# State Management Design

The HA integration categorizes Lumagen device state into three tiers based
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
| Input labels     | ZQS1*   | 40 labels (A0-D9), set via Lumagen menus      |
| Mode/CMS/Style labels | ZQS1* | 24 labels (custom mode, CMS, style)       |

**When fetched:**
- First-ever setup (no stored data) — automatic with backoff retry.
- User presses the "Refresh config" button entity.

**Why not on every startup:** Labels alone require 64 sequential queries
with 2-second timeouts each. The device can be slow to respond after
boot, causing timeouts and retries. Since these values almost never
change, caching them avoids unnecessary device traffic and startup delays.

## 2. Per-input runtime state (fetched on input change and power-on)

Output configuration that depends on which input is selected. The Lumagen
stores different output settings per input, so these must be re-fetched
when the user switches inputs.

| Data           | Command | Notes                          |
|----------------|---------|--------------------------------|
| Output mode    | ZQI18   | Custom mode C0-C7 or direct    |
| Output CMS     | ZQI18   | Also in ZQI24 unsolicited      |
| Output style   | ZQI18   | Also in ZQI24 unsolicited      |

**When fetched:**
- On power-on (as part of `fetch_runtime_state`).
- Automatically when the coordinator detects `logical_input` has changed.
- On reconnect after connection loss.

## 3. Signal state (unsolicited + keepalive)

Volatile state that changes as the source signal changes or the user
switches inputs. The Lumagen reports this automatically when configured
with "Report mode changes: Full v4".

| Data                        | Source       |
|-----------------------------|--------------|
| Power on/off                | Unsolicited sentinels (`Power-up complete.` / `POWER OFF.`) |
| Input selection             | ZQI24 unsolicited (v3+ fields II/KK), ZQI00 keepalive |
| Input memory bank           | ZQI00 keepalive only |
| Source resolution/rate      | ZQI24 unsolicited |
| Source aspect (raster/content/detected) | ZQI24 unsolicited |
| Source dynamic range (SDR/HDR) | ZQI24 unsolicited |
| Output resolution/rate/aspect | ZQI24 unsolicited |
| Output colorspace           | ZQI24 unsolicited |
| NLS status                  | ZQI24 unsolicited |

**Keepalive:** When the connection has been idle for 30 seconds (no data
received at all), a ZQI00 probe is sent. Any received data — including
unsolicited ZQI24 reports — resets the idle timer. This means during
active use (source changes, input switches), no keepalive traffic is
generated; the device's own reports prove liveness.

## Startup sequence

1. Connect to device, wait 3 seconds for TCP session to establish.
2. Load config state from HA storage (identity, game mode, labels).
3. Query power (ZQS02) — always needed, it's volatile.
4. If power is on, fetch runtime state (ZQI00 + ZQI18 + ZQI24).
5. If no stored config exists (first setup), schedule background
   `refresh_config` to fetch identity, game mode, and all labels.

On power-on (off to on transition detected from S02 response or
`Power-up complete.` sentinel):

1. Wait 10 seconds for the device to finish initialization.
2. Fetch runtime state (ZQI00 + ZQI18 + ZQI24).

Note: `None` to `on` transitions (initial state discovery after HA
restart or reconnect) do NOT trigger the power-on handler — the startup
sequence already handles this case.

## Connection lifecycle

- **Keepalive timeout:** If the ZQI00 probe gets no response within
  5 seconds (and no other data arrives), the connection is considered
  dead and a reconnect is initiated.
- **Reconnect:** Exponential backoff (1s, 2s, 4s, ... up to 30s). On
  reconnect, power + runtime state are re-fetched. Power state is NOT
  reset to None on disconnect, avoiding spurious power-on detection.
- **Idle tracking:** Uses `time.monotonic()` timestamp updated on every
  received line, not per-response events. This prevents false keepalive
  timeouts when the device is slow to respond (e.g., after boot).
