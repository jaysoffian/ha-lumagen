# Aspect Ratio Behavior Notes

Observations from live testing (2026-03-19) with a 1.78 source signal.

## Remote sends "Previous zoom" variants

The remote control always sends the "Previous zoom" RS232 commands, not the
"No zoom" variants documented in the command reference:

| Button | RS232 sent | Type          |
|--------|-----------|---------------|
| 4:3    | `n`       | Previous zoom |
| 16:9   | `w`       | Previous zoom |
| 1.85   | `j`       | Previous zoom |
| 2.35   | `W`       | Previous zoom |
| Lbox   | `l`       | Previous zoom |
| 1.90   | `A`       | (only variant) |
| 2.00   | `C`       | (only variant) |
| 2.20   | `E`       | (only variant) |
| 2.40   | `G`       | (only variant) |

The "No zoom" variants (`[`, `]`, `*`, `/`, `K`) force letterbox zoom off as
a side effect.  The "Previous zoom" variants preserve the existing zoom
setting, which is less surprising for automation.

## NLS is a standalone toggle

`N` toggles NLS on/off independent of the current aspect ratio.  The compound
commands like `*N` (16:9 + NLS) are just convenience shortcuts equivalent to
pressing the aspect button then the NLS button.

- Selecting a new aspect ratio clears NLS (except 1.85 — see below).
- AA Enable (`~`) clears NLS.

## 1.85 remembers NLS

Unique among all aspect ratios, 1.85 remembers its NLS state.  If you enable
NLS while on 1.85, switch to another aspect, then switch back to 1.85, NLS is
automatically re-enabled.  No other aspect ratio behaves this way.  Even AA
Enable does not clear this sticky state — pressing 1.85 afterward still
recalls NLS.

## Letterbox is not an aspect ratio

The Lbox button (`l`) is a signal format hint, not an aspect ratio selection.
It tells the Lumagen the source is letterboxed:

- Sets raster aspect to 1.33
- Sets content aspect to the source aspect (e.g. 1.78)
- AA remains off
- Pressing Lbox a second time is idempotent (no change)
- NLS can be toggled on top of Letterbox mode ("LBOXNLS")

## I25 response fields

The NLS state is visible in I25 field index 8: `N` = active, `-` = inactive.
Raster aspect is at indices 5-6, content aspect at indices 6-7 (three-digit
values like `178`, `185`, `235`).

## AA Enable / AA Disable

- AA Enable (`~`) switches to auto aspect detection and clears NLS.
- AA Disable (`V`) — not tested in this session.
