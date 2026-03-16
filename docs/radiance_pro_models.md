# Lumagen Radiance Pro Model Cheat Sheet

## All Models

| Model | Inputs | Outputs | Case | Notes |
|-------|--------|---------|------|-------|
| **4140** † | 1 × 18G | 1 × 9G | Compact | |
| **4140-18G** † | 1 × 18G | 1 × 18G | 1U rack | |
| **4240-C+** | 2 × 18G | 2 × 9G video | Compact | |
| **4240-C-18G** | 2 × 18G | 1 × 18G video, 1 × audio | Compact | |
| **4240+** | 2 × 18G | 2 × 9G video | 1U rack | |
| **4240-18G** | 2 × 18G | 1 × 18G video, 1 × audio | 1U rack | |
| **4242-18G** | 4 × 18G | 1 × 18G video, 1 × audio | 1U rack | |
| **4244-18G** † | 6 × 18G | 1 × 18G video, 1 × audio | 1U rack | 44XX board, depopulated |
| **4246-18G** † | 8 × 18G | 1 × 18G video, 1 × audio | 1U rack | 44XX board, depopulated |
| **4444-18G** † | 6 × 18G | 2 × 18G video, 2 × audio | 1U rack | PiP/PoP capable |
| **4446-18G** † | 8 × 18G | 2 × 18G video, 2 × audio | 1U rack | PiP/PoP capable |
| **5244** † | 6 × 18G | 1 × 18G, 1 × 9G | 1U rack | Ultra-low jitter |
| **5348** | 10 × 18G | 2 × 18G video, 1 × audio | 1U rack | Ultra-low jitter |

† Discontinued as of 2026 but still supported with free software updates.

## 4XXX vs 5XXX Series

All models share the same video processing quality — the difference is the output clock:

- **4XXX** — Low HDMI output jitter. Typical placement: after the audio processor.
- **5XXX** — Ultra-low HDMI output jitter (~10 pS as measured by Tektronix).
    Ideal placement: before the audio processor, providing a cleaner clock to the DACs for improved audio quality.

## Model Number Decoding

Model numbers follow the pattern **SO4I** (e.g. **4242**, **5348**):

| Position | Meaning |
|----------|---------|
| **S** (1st) | **Series** — `4` = standard low-jitter output, `5` = ultra-low-jitter output |
| **O** (2nd) | **Outputs** — total HDMI output port count, including audio-only ports (1–4) |
| **4** (3rd) | Always `4` — the Radiance Pro 4K line |
| **I** (4th) | **Inputs** — the number of HDMI inputs minus 2 (i.e. inputs = I + 2). `0` = 2, `2` = 4, `4` = 6, `6` = 8, `8` = 10 |

The 4140 is the one exception: I = 0 but it has only 1 input (a minimal single-port compact model).

### Suffixes

| Suffix | Meaning |
|--------|---------|
| **+** | 9 GHz output card — both output ports carry video (2 × 9G video) |
| **-18G** | 18 GHz output card — one port is full-bandwidth 18 GHz video, the other becomes audio-only (the 18G card uses both lanes for a single high-bandwidth port) |
| **-C** | Compact (non-rack-mountable) case |

Suffixes combine: e.g. **4240-C+** = compact case, 9 GHz outputs;
**4240-C-18G** = compact case, 18 GHz output.

### I/O Card Architecture

Standard (non-compact) models use dual-port HDMI cards — each card provides two HDMI ports. The last digit of the model number increments by 2 for each additional dual-port input card installed.

The **44XX** mainboard supports PiP/PoP (Picture-in-Picture/Picture-on-Picture).

The **42XX** models (including 4244 and 4246, which use a 44XX board with depopulated chips) do not support PiP/PoP.

## Key Specifications (All Models)

- HDMI 2.0, HDCP 1.X and 2.3
- 12-bit 4:2:2 video pipeline
- HDR10, HLG Dynamic Tone Mapping
- Compatible with Dolby LLDV (Lossless Dolby Vision)
- Darbee DVP enhancement (up to 1080p60)
- 4913-point (17×17×17) 3D LUT color management
- 21-point parametric grayscale calibration
- FPGA-based — hardware features added via free software updates
- Less than 35 W power consumption
- 2-year limited warranty, extendable to 5 years

## Sources

- [Lumagen Radiance Pro product page (archive.org)](https://web.archive.org/web/20250722080113/https://www.lumagen.com/products-sales/p/radiancepro-series-ultrahd-video-processor)
- [Lumagen Radiance Pro details (archive.org)](https://web.archive.org/web/20241006154541/http://www.lumagen.com/testindex.php?module=radiancepro_details)
- [Curt Palme — Radiance / ArtisaN Video Processors](https://www.curtpalme.com/Radiance.shtm)
- [AVS Forum — New Lumagen Radiance Pro Series](https://www.avsforum.com/threads/new-lumagen-radiance-pro-series.2172017/)
