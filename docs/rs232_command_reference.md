# Lumagen Radiance Pro — RS-232 Command Reference

Sources:
- [Tech Tip 11 - Radiance RS-232 control (11/20/2023)](https://www.lumagen.com/s/Tip0011_RS232CommandInterface_111023.pdf)
- [Radiance Pro firmware changelog](https://www.lumagen.com/software-updates/radiance-pro-updates)

This is a reference for building a TCP client that talks to a Lumagen Radiance Pro via a TCP/IP to Serial adapter (e.g. Global Cache IP2SL or USR-TCP232-302) connected to the Lumagen's RS-232 port. The adapter must provide bidirectional transparent bridging between network and serial. Data transfer must not be interpreted or altered in any way by the adapter.

---

## Connection & Protocol

### Protocol Notes

- Most commands are bare ASCII — just send the bytes, **no carriage return**.
- Commands marked with `<CR>` **require** a carriage return (`\r`, 0x0D) terminator. Sending `<CR>` on commands that don't need it brings up the Info page.
- `{` can be used as an alternative terminator in place of `<CR>`.
- `_` (underscore) is a no-op, always ignored.
- Any byte outside hex 20–7A acts as a terminator. Bytes above 0x7F are masked with 0x7F.
- Multi-character commands (e.g. `*N`) can be sent without delay between characters.
- **Echo**: With Echo=On (the assumed setting), the Lumagen echoes every byte it receives back to the sender. A query like `ZQS00` produces the byte stream `ZQS00!S00,Ok\r\n` — the echoed command bytes concatenated with the response. Clients must strip the echoed prefix before parsing the response. Lumagen recommends Echo=On; if set to Off, software updates may not work. For completeness, the available echo settings are:
    - On (default) — echo all characters sent to it.
    - Off — only send a message at power on/off.
    - Off with Status — send power/input changes in `ZQS02` / `ZQI00` format.
- The Lumagen sends unsolicited information upon various state changes (power on, power off, video signal changes) depending upon its configuration. An event driven client should be prepared to receive these updates and update itself accordingly.
- The Lumagen also sends messages as it is operated by IR or by other clients connected to the TCP-to-serial adapter.
- **Power on/off messages**: When the Lumagen powers on with echo enabled, it sends `Power-up complete.\r\n`. When powering off (standby), it sends `POWER OFF.\r\n`. These can be used as sentinels to confirm the operation completed.
- **Power On/Off Message (OnMessage/OffMessage)**: Can send an ASCII string out the RS-232 port to turn on or off a display. Enabling this turns off echoing of the original query command (the query response is still sent). It is recommended these messages are turned off.
- **Delimiter mode**: This reference assumes delimiters are off, as recommended by Lumagen. Having no delimiters works reliably and is easier to implement.

### RS-232 Link Commands

| Command | Description |
|---------|-------------|
| `ZD<0-3>` | Set delimiter mode (0=off, 1=on, 2=ack/nack, 3=checksum+ack/nack) — **no `<CR>`** |
| `ZE<0-2>` | Set echo (0=off, 1=on, 2=off+status) — **no `<CR>`** |
| `ZW<xxx><CR>` | Delay processing xxx ms (max 30000) |
| `ZYSX<CR>` | Set baud (D=9.6k, M=28.8k, F=57.6k, 1=115.2k, 2=230.4k, 3=460.8k) |

### Baud Rate Switching over TCP

The Lumagen defaults to 9600 baud. For faster communication, you can switch both the Lumagen and the TCP-to-serial adapter to a higher speed. This is not needed for simple remote control, but may be beneficial for configuration backup/restore. (Not documented here.)

**Order matters:** send the Lumagen baud command and the adapter baud command back-to-back in the same TCP write, so the adapter forwards the Lumagen command at the old speed before switching itself.

#### Lumagen baud command

`ZYSX<CR>` where X is:

| X | Baud |
|---|------|
| `D` | 9600 (default) |
| `M` | 28800 |
| `F` | 57600 |
| `1` | 115200 |
| `2` | 230400 |
| `3` | 460800 |

Return to 9600 before using Lumagen update utilities.

#### USR-TCP232-302 baud command

The USR-TCP232-302/E2 accepts a binary serial-port reconfiguration packet:

```
Header:  0x55 0xAA 0x55
Payload: 3-byte big-endian baud rate + 1 byte data format (0x03 = 8N1)
Trailer: 1-byte checksum (sum of payload bytes mod 256)
```

Example for 115200 baud (0x01C200):

```
55 AA 55  01 C2 00 03  C6
```

See "USR-TCP232-E2 User Manual" V1.1.3, pages 50–51.

---

## ASCII Commands — Power & Navigation

| RS232 | Description |
|-------|-------------|
| `%` | Power on |
| `$` | Power to standby |
| `M` | Activate menu |
| `X` | Exit / cancel |
| `!` | Force menu off |
| `k` | OK / accept |
| `<CR>` | OK / accept (only when command specifies it) |
| `<` | Left arrow |
| `>` | Right arrow |
| `v` | Down arrow |
| `^` | Up arrow |
| `0`–`9` | Digit entry |
| `U` | On-screen help |

## ASCII Commands — Input Selection

| RS232 | Description |
|-------|-------------|
| `i` | Choose input — e.g. `i2` for input 2, `i+2` for input 12 |
| `+` | Add 10 to next digit for input selection |
| `P` | Previous input |
| `L` | Output zone select |
| `#` | ALT key |

## ASCII Commands — Source Aspect

| RS232 | Aspect | Notes |
|-------|--------|-------|
| `n` | 1.33 | Previous zoom\* |
| `[` | 1.33 | No zoom |
| `l` | Letterbox | Previous zoom\* |
| `]` | Letterbox | No zoom |
| `w` | 1.78 | Previous zoom\* |
| `*` | 1.78 | No zoom |
| `j` | 1.85 | Previous zoom\* |
| `/` | 1.85 | No zoom |
| `A` | 1.90 | |
| `C` | 2.00 | |
| `E` | 2.20 | |
| `W` | 2.35 | Previous zoom\* |
| `K` | 2.35 | No zoom |
| `G` | 2.40 | |
| `N` | NLS toggle | Send source aspect first |
| `V` | Auto Aspect Disable | |
| `~` | Auto Aspect Enable | |

\* Lumagen Remote Control uses Previous Zoom variants.

### Extended Aspects

| RS232 | Aspect |
|-------|--------|
| `+n` | 1.33 |
| `+l` | 1.37 |
| `+w` | 1.66 |
| `+j` | 2.10 |
| `+W` | 2.55 |
| `+N` | 2.76 |

**Note**: These aspects require extended aspect ratios to be enabled (MENU → Input → Options → Aspect Setup → Aspect Opts → Extended).

## ASCII Commands — Memory & Display

| RS232 | Description |
|-------|-------------|
| `a` | Select Memory A |
| `b` | Select Memory B |
| `c` | Select Memory C |
| `d` | Select Memory D |
| `g` | Onscreen messages on |
| `s` | Onscreen messages off |
| `S` | Save shortcut (then send `k` to confirm) |
| `Y` | HDR Setup menu |
| `H` | Show test pattern |

## ASCII Commands — PIP

| RS232 | Description |
|-------|-------------|
| `e` | PIP off |
| `p` | PIP select |
| `r` | PIP swap |
| `m` | PIP mode |

## ASCII Commands — Legacy Test Patterns

| RS232 | Description |
|-------|-------------|
| `tXMM` | Use `ZY7T` instead |
| `tA` | Set adjustable test pattern mode (affected by output CMS settings). Also see `ZY7T` |
| `tR` | Set reference test pattern mode (affected only by PC/Video output setting). Also see `ZY7T` |

---

## Query Commands

### Query Protocol

- All queries: `ZQ` + category (`I`, `S`, `O`) + two-digit code. **No terminator.**
- Response: `!` + last 3 chars of query + comma-separated data + `\r\n`
- Ack/Nack (`!Y` / `!N`): terminated `\n\r` (0x0A 0x0D) — note reversed order.

### System Queries (ZQS)

| Command | Description | Example Response |
|---------|-------------|-----------------|
| `ZQS00` | Alive check | `!S00,Ok` |
| `ZQS01` | Device ID | `!S01,RadianceXD,102308,1009,745` (model, sw rev, model#, serial#) |
| `ZQS02` | Power state | `!S02,0` (off) / `!S02,1` (on) |
| `ZQS03` | Zoom step % | 5 or 15 |
| `ZQS04` | Trigger status (units with output triggers only) | `!S04,<trig1>,<trig2>` (0=low, 1=high) |
| `ZQS05`–`ZQS09` | Reserved | |

#### Labels (ZQS1XY)

Given command `ZQS1XY`, X and Y determine which label you're querying. The maximum label length varies per label type.

| X | Y | Label | Max Length |
|---|---|-------|-----------|
| `A`, `B`, `C`, or `D` | 0–9 | Input label 0–9 for MEMA, MEMB, MEMC, or MEMD. | 10 characters |
| `1` | 0–7 | Custom mode label 0–7 | 7 characters |
| `2` | 0–7 | CMS label 0–7 | 8 characters |
| `3` | 0–7 | Style label 0–7 | 8 characters |

To enumerate all labels, loop over:

    for x in "ABCD":
        # Loop over input labels in reverse to work-around bug in Lumagen firmware
        for y in reversed(range(10)):
            get_label(f"{x}{y}")
    for x in "123":
        for y in range(8):
            get_label(f"{x}{y}")

Example responses:

- `!S1A,Input`
- `!S11,Custom0`
- `!S12,CMS0`
- `!S13,2.40`

Note that the `ZQS1` response does not include the label slot (`Y`), so the client has to keep track of which label it most recently queried. Clients should _not_ try to parse unsolicited label responses (i.e. responses to a different client) nor rely on their own query being echoed back in the response.

### Input Queries (ZQI)

| Command | Description | Response |
|---------|-------------|----------|
| `ZQI00` | Basic input info | `!I00,<logical 1-18>,<mem A-D>,<physical 1-18>` |
| `ZQI01` | Input video | `!I01,<status>,<vrate*100>,<hres>,<vres>,<interlaced>,<3d>,<input_3d>` |
| `ZQI02` | Test pattern info | `!I02,<on>,<group>,<sub>,<IRE>,<A or R>` |
| `ZQI03` | Use `ZQI18` instead | |
| `ZQI04` | Audio select | 0–5=HDMI, 6–11=coax, 12–13=optical, 14–17=stereo |
| `ZQI05`\* | Black level | -64 to 64 |
| `ZQI06`\* | Contrast | -127 to 127 |
| `ZQI07`\* | Color format | 0=auto, 1=Bt.601, 2=Bt.709 |
| `ZQI08`\* | Color offset | -127 to 127 |
| `ZQI09`\* | Color red offset | -127 to 127 |
| `ZQI10`\* | Color grn offset | -127 to 127 |
| `ZQI11`\* | Hue offset | -127 to 127 |
| `ZQI12`\* | Hue red offset | -127 to 127 |
| `ZQI13`\* | Hue grn offset | -127 to 127 |
| `ZQI14`\* | YC delay | `<cr>,<cb>` (-31 to 31, units of 1/16 pixel) |
| `ZQI15` | Deinterlacing | 0=auto, 1=film, 2=video |
| `ZQI16` | Vertical shift | `<index>,<value>` (0=off, 1–15; -511 to 511) |
| `ZQI17` | Reinterlacing | `<enable>,<allow_keys>,<active>` (each 1/0) |
| `ZQI18` | Output config for current input | `!I18,<out1>,<out2>,<mode>,<3d>,<cms>,<style>` |
| `ZQI19` | Use `ZQI20` instead | |
| `ZQI20` | Input aspect | `!I20,<code><nls>` — code=0–9, nls='N' or '-' |
| `ZQI21`–`ZQI25` | See [Information Queries](#information-queries-zqi21zqi25) below |
| `ZQI26`–`ZQI29` | Reserved |
| `ZQI30` | Sharpness | Values per `ZY521ELS` format |
| `ZQI31`–`ZQI49` | Reserved |
| `ZQI50` | Rec 2020 support | `!I50,Y` or `!I50,N` — for the display connected to the main video output (Output 4 on 44XX, Output 2 on 42XX) |
| `ZQI51` | HDR test pattern Info Frame data | `!I51,P0X,P0Y,P1X,P1Y,P2X,P2Y,WPX,WPY,MAX,MIN,CLL,FALL` |
| `ZQI52` | HDR status | `!I52,<V>,<Min>,<Max>,<Cll>` (V: 0=SDR, 1=HDR) |
| `ZQI53` | Game mode | 0=off, 1=on |
| `ZQI54` | Auto aspect status | 0=off, 1=on |
| `ZQI55`–`ZQI99` | Reserved |

\* Input setting is combined with output setting; final value clamped to register max.

#### ZQI02 Test Pattern Groups

| Group | Sub | Pattern |
|-------|-----|---------|
| `a` | 0 | Crosshatch |
| `a` | 1 | Overscan |
| `a` | 2 | AspectSquares |
| `b` | 0 | Contrast1 |
| `b` | 2 | Contrast2 |
| `b` | 3 | BlkRamp |
| `b` | 4 | LowClip |
| `b` | 5 | WhtRamp |
| `b` | 6 | HiClip |
| `b` | 7 | Targets |
| `b` | 8 | Check |
| `b` | 9 | Icheck |
| `b` | 10 | VidBlack |
| `b` | 11 | VidWhite |
| `c` | 0 | HLines |
| `c` | 1 | VLines |
| `d` | 0 | Ramp |
| `e` | 0 | GrayWindowMed |
| `e` | 1 | GrayWindowSm |
| `e` | 2 | GraySolid |
| `f` | 0 | 100% ColorBars |
| `f` | 1 | 75% ColorBars |
| `g` | 0 | RedWindowMed |
| `g` | 1 | RedWindowSm |
| `g` | 2 | RedSolid |
| `h` | 0 | GrnWindowMed |
| `h` | 1 | GrnWindowSm |
| `h` | 2 | GrnSolid |
| `i` | 0 | BluWindowMed |
| `i` | 1 | BluWindowSm |
| `i` | 2 | BluSolid |
| `j` | 0 | YelWindowMed |
| `j` | 1 | YelWindowSm |
| `j` | 2 | YelSolid |
| `k` | 0 | CynWindowMed |
| `k` | 1 | CynWindowSm |
| `k` | 2 | CynSolid |
| `l` | 0 | MagWindowMed |
| `l` | 1 | MagWindowSm |
| `l` | 2 | MagSolid |
| `m` | 0 | DesaturatedRedWinMed |
| `m` | 1 | DesaturatedRedWinSm |
| `m` | 2 | DesaturatedRedWinSolid |
| `n` | 0 | DesaturatedGrnWinMed |
| `n` | 1 | DesaturatedGrnWinSm |
| `n` | 2 | DesaturatedGrnWinSolid |
| `o` | 0 | DesaturatedBluWinMed |
| `o` | 1 | DesaturatedBluWinSm |
| `o` | 2 | DesaturatedBluWinSolid |
| `p` | 0 | DesaturatedYelWinMed |
| `p` | 1 | DesaturatedYelWinSm |
| `p` | 2 | DesaturatedYelWinSolid |
| `q` | 0 | DesaturatedCynWinMed |
| `q` | 1 | DesaturatedCynWinSm |
| `q` | 2 | DesaturatedCynWinSolid |
| `r` | 0 | DesaturatedMagWinMed |
| `r` | 1 | DesaturatedMagWinSm |
| `r` | 2 | DesaturatedMagWinSolid |

Groups `m`–`r` (desaturated windows) are not in the menu; RS-232 control only.

#### ZQI18 Fields

| Field | Values |
|-------|--------|
| out1/out2 | 1=on, 0=off |
| mode | C0–C7 (config) or D*name* (direct mode) |
| 3d | 0=off, f=auto, 1=frame seq, 2=frame packed, 4=top-btm, 8=SbS |
| cms | 0–7 |
| style | 0–7 |

#### ZQI20 Aspect Codes

| Code | Aspect |
|------|--------|
| 0 | 4:3 |
| 1 | Letterbox |
| 2 | 16:9 |
| 3 | 1.85 |
| 4 | 2.35 |
| 5–7 | Reserved |
| 8 | ALT-1.85 (1.85 in 1.78 letterbox) |
| 9 | ALT-2.35 (= 2.40) |

#### ZQI51 Fields

Returns HDR test pattern Info Frame data (values set by `ZY540`–`ZY546`, returned even if not activated by `ZY547`):

| Field | Description |
|-------|-------------|
| P0X, P0Y | Display primary point 0 |
| P1X, P1Y | Display primary point 1 |
| P2X, P2Y | Display primary point 2 |
| WPX, WPY | White point |
| MAX, MIN | Mastering luminance max/min |
| CLL | Max content light level |
| FALL | Max frame average light level |

See CEA 861.3 for value definitions.

### Information Queries (ZQI21–ZQI25)

| Command | Description | Response |
|-------|-------------|-------------|
| `ZQI21` | Full      | `!I21,M,RRR,VVVV,D,X,AAA,SSS,Y,T,WWWW,C,B,PPP,QQQQ,ZZZ` |
| `ZQI22` | Full v2 |  Full + `,E,F,G,H` |
| `ZQI23` | Full v3 |  Full v2 + `,II,KK` |
| `ZQI24` | Full v4 |  Full v3 + `,JJJ,LLL` |
| `ZQI25` | Full v5 |  Full v4 + `,MEM,PWR` |

#### Information Response Fields

| Field | Description | Query Version |
|-------|-------------|-------------|
| M | 0=no source, 1=active video, 2=test pattern | All |
| RRR | Source vertical rate (e.g. 059=59.94, 060=60.00) | All |
| VVVV | Source vertical resolution (e.g. 1080=1080p) | All |
| D | Source 3D mode (0,1,2,4,8) | All |
| X | Input config number | All |
| AAA | Source raster aspect (e.g. 178=16:9) | All |
| SSS | Source content aspect (e.g. 240=2.40) | All |
| Y | '-'=normal, 'N'=NLS | All |
| T | Output 3D mode | All |
| WWWW | Outputs on — 16-bit hex, bit 0=out1, bit 1=out2, etc. | All |
| C | Output CMS (0–7) | All |
| B | Output Style (0–7) | All |
| PPP | Output vertical rate | All |
| QQQQ | Output vertical resolution | All |
| ZZZ | Output aspect | All |
| E | Output colorspace (0=601, 1=709, 2=2020, 3=2100) | v2+ |
| F | Source dynamic range (0=SDR, 1=HDR) | v2+ |
| G | Source mode (i=interlaced, p=progressive, -=no input) | v2+ |
| H | Output mode (I=interlaced, P=progressive) | v2+ |
| II  | Virtual input (1–19) | v3+ |
| KK | Physical input (1–19) | v3+ |
| JJJ | Detected raster aspect (e.g. 178 for HD or UHD) | v4+ |
| LLL | Detected content aspect (e.g. 240=2.40) | v4+ |
| MEM | Input memory (A, B, C, or D) | v5 |
| PWR | Power status (0=off, 1=on) | v5 |

**Notes**:
- Parsers should tolerate additional comma-delimited fields appended to the latest full info response that may be present in future firmware.
- The `ZQI21`–`ZQI25` response is also sent by the Lumagen unsolicited whenever it detects mode changes, depending upon the "report mode changes" setting.

#### Report Mode Changes

When enabled (MENU → Other → I/O Setup → RS-232 Setup → Report mode changes), mode changes cause the unit to send an unsolicited string in the format of the selected query response.

| Setting | Response Format |
|---------|-----------------|
| Off | (none) |
| Input | `ZQI01` + `ZQI18` |
| Output | `ZQO01` |
| Full | `ZQI21` |
| Full v2 | `ZQI22` |
| Full v3 | `ZQI23` |
| Full v4 | `ZQI24` |
| Full v5 | `ZQI25` |

### Output Queries (ZQO)

| Command | Description | Response |
|---------|-------------|----------|
| `ZQO00` | Basic output info | `!O00,<config>,<vid1>,<vid2>,<aud1>,<aud2>` |
| `ZQO01` | Output mode | `!O01,<vrate*100>,<hres>,<vres>,<interlaced>,<3d>` |
| `ZQO02` | Output aspect | Current + 5 per-input aspects (110–250 = 1.10–2.50) |
| `ZQO03` | Output shrink | `<top>,<left>,<bottom>,<right>` (0–255 pixels) |
| `ZQO04` | Gamma | 80–140 (= 0.80–1.40). *Also see `ZY40`* |
| `ZQO05` | Color gamut enabled | 0 or 1. *Also see `ZY412`* |
| `ZQO06` | Use `ZQO30` instead | |
| `ZQO07` | Use `ZQO30` instead | |
| `ZQO08` | Use `ZQO30` instead | |
| `ZQO09` | Color temp IRE pts 0–10 | 11 values, 0–1000 (= 0.0–100.0). *See also `ZQO89`* |
| `ZQO10` | Color temp R pts 0–10 | 11 values, 0–1000 (= 0.0–100.0). *See also `ZQO90`* |
| `ZQO11` | Color temp G pts 0–10 | 11 values, 0–1000 (= 0.0–100.0). *See also `ZQO91`* |
| `ZQO12` | Color temp B pts 0–10 | 11 values, 0–1000 (= 0.0–100.0). *See also `ZQO92`* |
| `ZQO13` | Color settings | `<color>,<color_red>,<color_grn>` (-127 to 127) |
| `ZQO14` | Hue settings | `<hue>,<hue_red>,<hue_grn>` (-127 to 127) |
| `ZQO15` | Black/contrast | `<black>,<contrast>` (-64–64, -127–127) |
| `ZQO16` | Output mode name | Text string |
| `ZQO17` | CTemp points count | 2, 5, 11, 12, or 21 |
| `ZQO18` | Color format | 0=yc422, 1=yc444, 2=rgbvid, 3=rgbpc, 4=yc420 |
| `ZQO19` | Reserved | |
| `ZQO20` | 3D LUT capability | `!O20,<dim>,<bits>` |
| `ZQO21` | Current 3D LUT size | 01, 05, 09, or 17 |
| `ZQO22`–`ZQO29` | Reserved | |
| `ZQO30XXYYZZ` | Read 3D LUT value | `!O30,<rrrr>,<gggg>,<bbbb>` (hex, 0x0000–0x0400) |
| `ZQO31`–`ZQO88` | Reserved | |
| `ZQO89` | Color temp IRE pts 11–20 | 12pt: point 12; 21pt: points 11–20. *See also `ZQO09`* |
| `ZQO90` | Color temp R pts 11–20 | 12pt: point 12; 21pt: points 11–20. *See also `ZQO10`* |
| `ZQO91` | Color temp G pts 11–20 | 12pt: point 12; 21pt: points 11–20. *See also `ZQO11`* |
| `ZQO92` | Color temp B pts 11–20 | 12pt: point 12; 21pt: points 11–20. *See also `ZQO12`* |
| `ZQO93`–`ZQO99` | Reserved | |

---

## Set Commands (ZY) — All require `<CR>` terminator

### Output Settings

| Command | Description |
|---------|-------------|
| `ZY0M<CR>` | Zoom factor (0–2, or 0–7 with 5% steps) |
| `ZY1MMM<CR>` | Output aspect for all inputs (110–250) |
| `ZY2MMMNNNOOOPPP<CR>` | Output shrink (top, left, bottom, right; 0–255) |
| `ZY3<1,2><H,L><CR>` | Set trigger (H=on, L=off) |
| `ZY40XXX<CR>` | Gamma (080–140) |
| `ZY44<ModeName><CR>` | Set output mode by name |
| `ZY45XMMM<CR>` | Output aspect per input aspect (X: 0=4:3, 1=Lbox, 2=16:9, 3=1.85, 4=2.35; MMM: 110–250) |
| `ZY46F<CR>` | Output format (0=YCB422, 1=YCB444, 2=RGBPC, 3=RGBVID, 8=automax, 9=auto9) |
| `ZY46FC<CR>` | Output format + colorspace (C: 0=auto, 1=601, 2=709, 3=hdr2020, 4=sdr2020, 5=sdrP3; add 8 for HDR flag) |
| `ZY47X<CR>` | 3D eye output (L/R/B) |
| `ZY48X<CR>` | 3D eyeglass polarity (+/-) |

### Output Mode / CMS / Style

| Command | Description |
|---------|-------------|
| `ZY530MCS<CR>` | Set mode(M), CMS\(C\), style(S) — each 0–7 or K=keep |
| `ZY530MCDS<CR>` | Mode(M), CMS-SDR\(C\), CMS-HDR(D), style(S) |

### Output Color / Hue / Black / Contrast

| Command | Description |
|---------|-------------|
| `ZY43CCSVVV<CR>`\* | Color (S=+/-, VVV=000–127) |
| `ZY43CRSVVV<CR>`\* | Color red |
| `ZY43CGSVVV<CR>`\* | Color green |
| `ZY43HHSVVV<CR>`\* | Hue |
| `ZY43HRSVVV<CR>`\* | Hue red |
| `ZY43HGSVVV<CR>`\* | Hue green |
| `ZY43BLSVVV<CR>`\* | Black (000–064) |
| `ZY43COSVVV<CR>`\* | Contrast (000–127) |

### Output Color Management (3D LUT)

| Command | Description |
|---------|-------------|
| `ZY410CRXXXX<CR>` | Use `ZY415` instead |
| `ZY411<CR>` | Reset color gamut to defaults + 8pt mode |
| `ZY412<0,1><CR>` | 3D gamut enable/disable |
| `ZY413XX<CR>` | Set 1D LUT points (11, 12, or 21) — resets all points |
| `ZY415XXYYZZCVVVV<CR>` | Write 3D LUT — XX,YY,ZZ=address, C=0/1/2 (R/G/B), VVVV=hex 0000–0400 |
| `ZY416XX<CR>` | Gamut size (05, 09, 17) |
| `ZY416XXM<CR>` | Gamut size + gamma mode (M='S' source, 'L' linear) |
| `ZY417XXXXXG<CR>` | HDR intensity mapping (00000=off, 00050–10000=max nits; G='A'/'H'/'S') |
| `ZYGXYZRRRGGGBBB<CR>` | Short 3D LUT write — single-char addresses (10–16 = `:;<=>?@`) |

### Output Color Temperature (1D LUT)

| Command | Description |
|---------|-------------|
| `ZY42APPRRRRGGGGBBBB<CR>` | Set R,G,B for point PP (0000–1000 = 0.0–100.0; optional 5-digit) |
| `ZY42RPPXXXX<CR>` | Set red for point PP |
| `ZY42GPPXXXX<CR>` | Set green for point PP |
| `ZY42BPPXXXX<CR>` | Set blue for point PP |
| `ZY42IPPXXXXX<CR>` | Set IRE for point PP |
| `ZY42DPP<CR>` | Reset point PP to default |

### Input Settings

| Command | Description |
|---------|-------------|
| `ZY503XYZ<CR>` | Use `ZY530` instead |
| `ZY506SVVV<CR>`\* | Input contrast (S=+/-, VVV=000–127) |
| `ZY507X<CR>`\* | Input color format (0=auto, 1=Bt.601, 2=Bt.709) |
| `ZY508SVVV<CR>`\* | Input color offset |
| `ZY509SVVV<CR>`\* | Input color red offset |
| `ZY510SVVV<CR>`\* | Input color grn offset |
| `ZY511SVVV<CR>`\* | Input hue offset |
| `ZY512SVVV<CR>`\* | Input hue red offset |
| `ZY513SVVV<CR>`\* | Input hue grn offset |
| `ZY514SXXSYY<CR>`\* | Input YC delay (Cr, Cb; 00–31 in 1/16 pixel) |
| `ZY515X<CR>` | Deinterlacing (0=auto, 1=film, 2=video) |
| `ZY5160XX<CR>` | Select vertical shift (0=off, 1–15) |
| `ZY5161XXSVVV<CR>` | Select + set vertical shift (S=+/-, VVV=0–511) |
| `ZY517GGGME<CR>` | Darbee (GGG=000–120 or relative +/-01–99 or KKK; M=P/G/H/K; E=0/1/K) |
| `ZY518PRRSCTGGBB<CR>` | HDR mapping (P=group, RR=ratio 31–95, S=shape 0–7, C=clip 0–7, T=trans 0–7, GG=gamma 8–24, BB=black 1–15) |
| `ZY520X<CR>` | Toggle HDMI hotplug (X=0–7 for inputs 1–8, 'A'=all) |
| `ZY521ELS<CR>` | Sharpness (E=Y/N enable, L=0–7 level, S=H/N sensitivity) |
| `ZY522EnHnVS<CR>` | H/V sharpness (n=+/-, H,V=0–7, S=H/N) |
| `ZY523X<CR>` | Reinterlace arrow key control (0=disallow, 1=allow, 2=allow with OSD) |

### Setting Labels

Given command `ZY524{X}{Y}{label}`, X and Y determine which label you're setting to "label". The maximum label length varies per label type. The Lumagen truncates overlong labels.

| Command | Description | Max Length |
|---------|-------------|------------|
| `ZY524XYlabel<CR>` | Set input label X (memory 'A'-'D' or '0' for all) on input Y ('0'-'9') to "label" | 10 characters |
| `ZY5241Ylabel<CR>` | Set custom mode label Y ('0'-'7') to "label" | 7 characters |
| `ZY5242Ylabel<CR>` | Set CMS label Y ('0'-'7') to "label" | 8 characters |
| `ZY5243Ylabel<CR>` | Set style label Y ('0'-'7') to "label" | 8 characters |

### Auto Aspect / Game Mode

| Command | Description |
|---------|-------------|
| `ZY550<CR>` | Reset auto aspect detection |
| `ZY551X<CR>` | Game mode (0=off, 1=on) |
| `ZY552X<CR>` | Set minimum fan speed (X=0–9 for speeds 1–10) |
| `ZY553X<CR>` | Subtitle shift (0=disable, 1=shift 3%, 2=shift 6%) |

### Display / OSD

| Command | Description |
|---------|-------------|
| `ZB<X>` | Define block char (rendered as `█`) — **no `<CR>`** |
| `ZC` | Clear OSD message — **no `<CR>`** |
| `ZTMxxxx<CR>` | Display message (M='0'–'8' timed, '9'=persistent; 2 lines, 30 chars/line) |
| `ZY418CRRGGBB<CR>` | Message colors (C: 0=bg, 1=fg, 2=blend; RRGGBB hex; blend uses only last digit 1–f) |
| `ZY811<CR>` | Pop up input and aspect on OSD |

### Test Patterns

| Command | Description |
|---------|-------------|
| `ZY7TGSIII<CR>` | Show pattern (G=group a–r, S=subpattern, III=IRE 000–100) |
| `ZY7TsSRRRGGGBBB<CR>` | User pattern (S=0/1/2 med/sm/full, RGB 0–255) |
| `ZY7TsSSSAAARRRGGGBBB<CR>` | User pattern + size/APL (SSS=area 0–999, AAA=APL 0–100) |
| `ZY532CSDM<CR>` | Test pattern output mode (C=CMS, S=style, D=3D, M=mode name/C0–C7/K) |
| `ZY533ICSDM<CR>` | Test pattern output mode + input colorspace (I=1 Rec709, 2 Rec2020) |

### HDR Info Frame

| Command | Description |
|---------|-------------|
| `ZY540XXXXYYYY<CR>` | Primary display point 0 (hex) |
| `ZY541XXXXYYYY<CR>` | Primary display point 1 |
| `ZY542XXXXYYYY<CR>` | Primary display point 2 |
| `ZY543XXXXYYYY<CR>` | White point |
| `ZY544XXXXYYYY<CR>` | Mastering luminance max/min |
| `ZY545XXXXYYYY<CR>` | Max CLL / max FALL |
| `ZY546<CR>` | Reset to defaults |
| `ZY547<CR>` | Activate ZY540–546 |
| `ZY548X<CR>` | HDR pass through (P) or programmed (T) |

### System

| Command | Description |
|---------|-------------|
| `ZY6SAVECONFIG<CR>` | Save to flash (exit test patterns first) |
| `ZY7M<0,1><CR>` | Menu position (0=default, 1=top) |

---

## Appendix: How Lumagen Inputs Work

The Radiance Pro has three layers of input abstraction:

### Physical Inputs

The number of physical HDMI input ports varies by model:

| Model | Physical Inputs | Outputs |
|-------|----------------|---------|
| 4140  | 1              | 1       |
| 4240  | 2              | 2       |
| 4242  | 4              | 2       |
| 4244  | 6              | 2       |
| 4246  | 8              | 2       |
| 4444  | 6              | 4       |
| 4446  | 8              | 4       |
| 5244  | 6              | 2       |
| 5348  | 10             | 3       |

### Logical (Virtual) Inputs

Each physical input can be mapped to one or more **logical inputs** (also called virtual inputs). The protocol supports up to 19 logical inputs. This allows a single physical port to appear as multiple sources with different settings (e.g. different aspect ratios or color profiles for the same HDMI port).

The remote selects logical inputs: buttons 1–9 select inputs 1–9, and the `+10` prefix accesses inputs 10–19 (e.g. `+10` then `0` selects input 10). On the 5348, pressing `0` without `+10` is a shortcut for input 10.

### Input (Configuration) Memories

The Radiance Pro has four input memories (MEMA, MEMB, MEMC and MEMD). Each input memory has sub-memories for each supported input resolution and rate which are automatically selected based on the input resolution and vertical-rate. The "Other" entry is selected for input resolutions and vertical rates not specified explicitly. Each input resolution and vertical rate has 8 sub-memories which are programmable on a per-input and per-input-memory basis. Different inputs and input memories can each be independently programed to one of the 8 sub-memories for each listed resolution and vertical rate.

Each input memory, and sub-memory, is independent of the other memories. To allow the memories to be used for mode selection (i.e. day/night), by default, the memory type remains unchanged when a new input is selected. (i.e. If input 2 memory B is active, pressing "INPUT, 3" selects input 3 memory B).

### Input Labels

Labels are stored per input memory, indexed 0–9 (label index 0 = logical input 1, index 9 = logical input 10). The label query `ZQS1{memory}{index}` retrieves them — e.g. `ZQS1A0` gets the label for input 1 in MEMA.

### Configuration Chain

Each input memory has sub-memories automatically selected by input resolution and 2D/3D mode. Each sub-memory links to an output **Mode** (0–7), **CMS** (0–7), and **Style** (0–7):

```
Logical Input → Input Memory (A-D) → Resolution Sub-memory → Mode + CMS + Style
```

By default all sub-memories point to Auto mode, CMS 0 (SDR) or CMS 1 (HDR), and Style 0.
