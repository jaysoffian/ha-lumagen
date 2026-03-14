# Lumagen Radiance Pro — RS-232 Command Reference

Source: [Tech Tip 11 - Radiance RS-232 control (11/20/2023)](https://www.lumagen.com/s/Tip0011_RS232CommandInterface_111023.pdf)

This is a reference for building a TCP client (e.g. for Home Assistant / Homebridge) that talks to a Lumagen Radiance Pro via a TCP-to-serial adapter (e.g. Global Cache IP2SL or USR-TCP232-302) connected to its RS-232 port. It is assumed that by connecting to the TCP-to-serial adapter over TCP, the connection faithfully echoes data to the RS-232 port and vice-versa.

## Prerequisites

The customer must configure their TCP-to-serial adapter to match the Lumagen's RS-232 settings. The default Lumagen RS232 port settings are 9600 bps 8n1:

- **Data Rate**: 9600 bps
- **Data Size**: 8 bits
- **Parity**: None
- **Stop Bits**: 1
- **Flow control**: None

The customer must also configure the Lumagen with the following RS-232 port related settings:

- **MENU → Other → I/O Setup → RS-232 Setup**:
    - **Echo**: On (The Radiance will echo all characters sent to it.)
    - **Delimiters**: Off
    - **Report mode changes**: Full v4 (The Radiance will send a string upon mode changes as if the respective query command was sent.)
- **MENU → Other → OnOff Setup**:
    - **OnMessage**: Off / Disabled (If set, turns off echoing of the original query command.)
    - **OffMessage**: Off / Disabled (If set, turns off echoing of the original query command.)

Extended aspect ratios (MENU → Input → Options → Aspect Setup → Aspect Opts → Extended) must also be enabled to detect to select/detect the following ratios: 4:3 Pillarbox, 1.375 Pillarbox, 1.66 Pillarbox, 2.10, 2.55, 2.76.

## Protocol Notes

- Most commands are bare ASCII — just send the bytes, **no carriage return**.
- Commands marked with `<CR>` **require** a carriage return (`\r`, 0x0D) terminator. Sending `<CR>` on commands that don't need it brings up the Info page.
- `{` can be used as an alternative terminator in place of `<CR>`.
- `_` (underscore) is a no-op, always ignored.
- Any byte outside hex 20–7A acts as a terminator. Bytes above 0x7F are masked with 0x7F.
- Multi-character commands (e.g. `*N`) can be sent without delay between characters.
- **Echo**: With Echo=On (the assumed setting), the Lumagen echoes every byte it receives back to the sender. A query like `ZQS00` produces the byte stream `ZQS00!S00,Ok\r\n` — the echoed command bytes concatenated with the response. Clients must strip the echoed prefix before parsing the response.
- The Lumagen sends unsolicited information upon various state changes (power on, power off, video signal changes) depending upon its configuration. An event driven client should be prepared to receive these updates and update itself accordingly.

---

## Commands — Power & Navigation

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

## How Lumagen Inputs Work

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

### Memory Banks

Each logical input has four independent **configuration memories** (MEMA, MEMB, MEMC, MEMD). Switching memory banks changes the active settings for all inputs — useful for day/night modes or different display configurations. Each memory bank has its own set of input labels.

### Input Labels

Labels are stored per memory bank, indexed 0–9 (label index 0 = logical input 1, index 9 = logical input 10). The label query `ZQS1{bank}{index}` retrieves them — e.g. `ZQS1A0` gets the label for input 1 in MEMA.

### Configuration Chain

Each input memory has sub-memories automatically selected by input resolution and 2D/3D mode. Each sub-memory links to an output **Mode** (0–7), **CMS** (0–7), and **Style** (0–7):

```
Logical Input → Memory Bank (A-D) → Resolution Sub-memory → Mode + CMS + Style
```

By default all sub-memories point to Auto mode, CMS 0 (SDR) or CMS 1 (HDR), and Style 0.

## Commands — Input Selection

| RS232 | Description |
|-------|-------------|
| `i` | Choose input — e.g. `i2` for input 2, `i+2` for input 12 |
| `+` | Add 10 to next digit for input selection |
| `P` | Previous input |
| `L` | Output zone select |
| `#` | ALT key |

## Commands — Source Aspect

| RS232 | Aspect | Notes |
|-------|--------|-------|
| `n` | 4:3 | Previous zoom |
| `[` | 4:3 | No zoom |
| `[N` | 4:3 NLS | No zoom |
| `l` | Letterbox | Previous zoom |
| `]` | Letterbox | No zoom |
| `]N` | Letterbox NLS | No zoom |
| `w` | 16:9 | Previous zoom |
| `*` | 16:9 | No zoom |
| `*N` | 16:9 NLS | No zoom |
| `j` | 1.85 | Previous zoom |
| `/` | 1.85 | No zoom |
| `/N` | 1.85 NLS | No zoom |
| `A` | 1.90 | Pro only |
| `AN` | 1.90 NLS | Pro only |
| `C` | 2.00 | Pro only |
| `CN` | 2.00 NLS | Pro only |
| `E` | 2.20 | Pro only |
| `EN` | 2.20 NLS | Pro only |
| `W` | 2.35 | Previous zoom |
| `K` | 2.35 | No zoom |
| `G` | 2.40 | Pro only |
| `N` | NLS toggle | Send source aspect first |
| `V` | Auto Aspect Disable | Pro only |
| `~` | Auto Aspect Enable | Pro only |

### Extended Aspects

| RS232 | Aspect |
|-------|--------|
| `+n` | 4:3 Pillarbox |
| `+l` | 1.375 Pillarbox |
| `+w` | 1.66 Pillarbox |
| `+j` | 2.10 |
| `+W` | 2.55 |
| `+N` | 2.76 |

**Note**: These aspects require extended aspect ratios to be enabled (MENU → Input → Options → Aspect Setup → Aspect Opts → Extended).

## Commands — Memory & Display

| RS232 | Description |
|-------|-------------|
| `a` | Select Memory A |
| `b` | Select Memory B |
| `c` | Select Memory C |
| `d` | Select Memory D |
| `g` | Onscreen messages on |
| `s` | Onscreen messages off |
| `S` | Save shortcut (then send `k` to confirm) |
| `Y` | HDR Setup menu  |
| `H` | Show test pattern  |

## Commands — PIP

| RS232 | Description |
|-------|-------------|
| `e` | PIP off |
| `p` | PIP select |
| `r` | PIP swap |
| `m` | PIP mode |

---

## Query Protocol

- All queries: `ZQ` + category (`I`, `S`, `O`) + two-digit code. **No terminator.**
- Response: `!` + last 3 chars of query + comma-separated data + `\r\n`
- Ack/Nack (`!Y` / `!N`): terminated `\n\r` (0x0A 0x0D) — note reversed order.

## Query Commands — System (ZQS)

| Command | Description | Example Response |
|---------|-------------|-----------------|
| `ZQS00` | Alive check | `!S00,Ok` |
| `ZQS01` | Device ID | `!S01,RadianceXD,102308,1009,745` (model, sw rev, model#, serial#) |
| `ZQS02` | Power state | `!S02,0` (off) / `!S02,1` (on) |
| `ZQS03` | Zoom step % | 5 or 15 |
| `ZQS04` | Trigger status | `!S04,<trig1>,<trig2>` (0=low, 1=high) |

### Query Command - Labels (ZQS1XY)

Given command `ZQS1XY`, X and Y determine which label you're querying.

| X | Y | Label |
|---|---|------------------|
| `A`, `B`, `C`, or `D` | 0–9 | Input label 0–9 for MEMA, MEMB, MEMC, or MEMD. |
| `1` | 0–7 | Custom mode  label 0–7 |
| `2` | 0–7 | CMS label 0–7 |
| `3` | 0–7 | Style label 0–7

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

## Query Commands — Input (ZQI)

| Command | Description | Response |
|---------|-------------|----------|
| `ZQI00` | Basic input info | `!I00,<logical 1-18>,<mem A-D>,<physical 1-18>` |
| `ZQI01` | Input video | `!I01,<status>,<vrate*100>,<hres>,<vres>,<interlaced>,<3d>,<input_3d>` |
| `ZQI02` | Test pattern info | `!I02,<on>,<group>,<sub>,<IRE>,<A or R>` |
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
| `ZQI20` | Input aspect | `!I20,<code><nls>` — code=0–9, nls='N' or '-' |
| `ZQI30` | Sharpness | Values per ZY521ELS format |
| `ZQI50` | Rec 2020 support (Pro) | `!I50,Y` or `!I50,N` |
| `ZQI52` | HDR status (Pro) | `!I52,<V>,<Min>,<Max>,<Cll>` (V: 0=SDR, 1=HDR) |
| `ZQI53` | Game mode | 0=off, 1=on |

\* Input setting is combined with output setting; final value clamped to register max.

### ZQI18 Fields

| Field | Values |
|-------|--------|
| out1/out2 | 1=on, 0=off |
| mode | C0–C7 (config) or D\<name\> (direct mode) |
| 3d | 0=off, f=auto, 1=frame seq, 2=frame packed, 4=top-btm, 8=SbS |
| cms | 0–7 |
| style | 0–7 |

### ZQI20 Aspect Codes

| Code | Aspect |
|------|--------|
| 0 | 4:3 |
| 1 | Letterbox |
| 2 | 16:9 |
| 3 | 1.85 |
| 4 | 2.35 |
| 8 | ALT-1.85 (1.85 in 1.78 letterbox) |
| 9 | ALT-2.35 (= 2.40) |

## Query Commands — Information (ZQI21, ZQI22, ZQI23, ZQI24)

| Command | Description | Response |
|-------|-------------|-------------|
| `ZQI21` | Full      | `!I21,M,RRR,VVVV,D,X,AAA,SSS,Y,T,WWWW,C,B,PPP,QQQQ,ZZZ` |
| `ZQI22` | Full v2 |  Full + `,E,F,G,H` |
| `ZQI23` | Full v3 |  Full v2 + `,II,KK` |
| `ZQI24` | Full v4 |  Full v3 + `,JJJ,LLL` |

### Information Response Fields

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
| E | Output colorspace (0=601, 1=709, 2=2020, 3=2100) | v2, v3, v4 |
| F | Source dynamic range (0=SDR, 1=HDR) | v2, v3, v4 |
| G | Source mode (i=interlaced, p=progressive, -=no input) | v2, v3, v4 |
| H | Output mode (I=interlaced, P=progressive) | v2, v3, v4 |
| II  | Virtual input (1–19) | v3, v4 |
| KK | Physical input (1–19) | v3, v4 |
| JJJ | Detected raster aspect (e.g. 178 for HD or UHD) | v4 |
| LLL | Detected content aspect (e.g. 240=2.40) | v4 |

**Notes**:
- Parsers should tolerate additional comma-delimited fields appended to the `ZQI24` (Full v4) response that may be present in future firmware.
- The `ZQI21`, `ZQI22`, `ZQI23`, or `ZQI24` response is also sent by the Lumagen unsolicited whenever it detects mode changes depending upon the "report mode changes" setting.

## Query Commands — Output (ZQO)

| Command | Description | Response |
|---------|-------------|----------|
| `ZQO00` | Basic output info | `!O00,<config>,<vid1>,<vid2>,<aud1>,<aud2>` |
| `ZQO01` | Output mode | `!O01,<vrate*100>,<hres>,<vres>,<interlaced>,<3d>` |
| `ZQO02` | Output aspect | Current + 5 per-input aspects (110–250 = 1.10–2.50) |
| `ZQO03` | Output shrink | `<top>,<left>,<bottom>,<right>` (0–255 pixels) |
| `ZQO04` | Gamma | 80–140 (= 0.80–1.40) |
| `ZQO05` | Color gamut enabled | 0 or 1 |
| `ZQO13` | Color settings | `<color>,<color_red>,<color_grn>` (-127 to 127) |
| `ZQO14` | Hue settings | `<hue>,<hue_red>,<hue_grn>` (-127 to 127) |
| `ZQO15` | Black/contrast | `<black>,<contrast>` |
| `ZQO16` | Output mode name | Text string |
| `ZQO17` | CTemp points count | 2, 5, 11, 12, or 21 |
| `ZQO18` | Color format (Pro) | 0=yc422, 1=yc444, 2=rgbvid, 3=rgbpc, 4=yc420 |
| `ZQO20` | 3D LUT capability | `!O20,<dim>,<bits>` |
| `ZQO21` | Current 3D LUT size | 01, 05, 09, or 17 |
| `ZQO30XXYYZZ` | Read 3D LUT value | `!O30,<rrrr>,<gggg>,<bbbb>` (hex, 0x0000–0x0400) |

---

## Set Commands (ZY) — All require `<CR>` terminator

### RS232 Configuration

| Command | Description |
|---------|-------------|
| `ZD<0-3>` | Set delimiter mode (0=off, 1=on, 2=ack/nack, 3=checksum+ack/nack) — **no `<CR>`** |
| `ZE<0-2>` | Set echo (0=off, 1=on, 2=off+status) — **no `<CR>`** |
| `ZW<xxx><CR>` | Delay processing xxx ms (max 30000) |
| `ZYSX<CR>` | Set baud (D=9.6k, M=28.8k, F=57.6k, 1=115.2k, 2=230.4k, 3=460.8k) |

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
| `ZY530MCS<CR>` | Set mode(M), CMS(C), style(S) — each 0–7 or K=keep |
| `ZY530MCDS<CR>` | Pro: mode(M), CMS-SDR(C), CMS-HDR(D), style(S) |

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
| `ZY411<CR>` | Reset color gamut to defaults + 8pt mode |
| `ZY412<0,1><CR>` | 3D gamut enable/disable |
| `ZY413XX<CR>` | Set 1D LUT points (11, 12, or 21) — resets all points |
| `ZY415XXYYZZCVVVV<CR>` | Write 3D LUT — XX,YY,ZZ=address, C=0/1/2 (R/G/B), VVVV=hex 0000–0400 |
| `ZY416XX<CR>` | Gamut size (05, 09, 17) |
| `ZY416XXM<CR>` | Gamut size + gamma mode (Pro; M='S' source, 'L' linear) |
| `ZY417XXXXXG<CR>` | HDR intensity mapping (00000=off, 00050–10000=max nits; G='A'/'H'/'S') |
| `ZYGXYZRRRGGGBBB<CR>` | Short 3D LUT write — single-char addresses (10–16 = `:;<=>?@`) |

### Output Color Temperature (1D LUT)

| Command | Description |
|---------|-------------|
| `ZY42APPRRRRGGGGBBBB<CR>` | Set R,G,B for point PP (0000–1000 = 0.0–100.0; optional 5-digit on Pro) |
| `ZY42RPPXXXX<CR>` | Set red for point PP |
| `ZY42GPPXXXX<CR>` | Set green for point PP |
| `ZY42BPPXXXX<CR>` | Set blue for point PP |
| `ZY42IPPXXXXX<CR>` | Set IRE for point PP |
| `ZY42DPP<CR>` | Reset point PP to default |

### Input Settings

| Command | Description |
|---------|-------------|
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
| `ZY520X<CR>` | Toggle HDMI hotplug (X=0–7 input, 'A'=all) |
| `ZY521ELS<CR>` | Sharpness (E=Y/N enable, L=0–7 level, S=H/N sensitivity) |
| `ZY522EnHnVS<CR>` | H/V sharpness (n=+/-, H,V=0–7, S=H/N) |
| `ZY524XYlabel<CR>` | Set label (X=A–D mem/0=all/1=mode/2=CMS/3=style; Y=index; label=text) |

### Auto Aspect / Game Mode

| Command | Description |
|---------|-------------|
| `ZY550<CR>` | Reset auto aspect detection |
| `ZY551X<CR>` | Game mode (0=off, 1=on) |

### Display / OSD

| Command | Description |
|---------|-------------|
| `ZB<X>` | Define block char (rendered as `█`) — **no `<CR>`** |
| `ZC` | Clear OSD message — **no `<CR>`** |
| `ZTMxxxx<CR>` | Display message (M='0'–'8' timed, '9'=persistent; 2 lines, 30 chars/line) |
| `ZY418CRRGGBB<CR>` | Message colors (C: 0=bg, 1=fg, 2=blend; RRGGBB hex; when setting blend value, only last B digit is used so range is 000001-00000f where ‘f’ is opaque messages and ‘1’ is near transparent. |

### Test Patterns

| Command | Description |
|---------|-------------|
| `ZY7TGSIII<CR>` | Show pattern (G=group a–r, S=subpattern, III=IRE 000–100) |
| `ZY7TsSRRRGGGBBB<CR>` | User pattern (S=0/1/2 med/sm/full, RGB 0–255) |
| `ZY7TsSSSAAARRRGGGBBB<CR>` | User pattern + size/APL (SSS=area 0–999, AAA=APL 0–100) |
| `ZY532CSDM<CR>` | Test pattern output mode (C=CMS, S=style, D=3D, M=mode name/C0–C7/K) |
| `ZY533ICSDM<CR>` | Pro: + input colorspace (I=1 Rec709, 2 Rec2020) |

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

## Addendum: Baud Rate Switching over TCP

The Lumagen defaults to 9600 baud. For faster communication (e.g. firmware updates),
you can switch both the Lumagen and the TCP/serial adapter to a higher speed.

**Order matters:** send the Lumagen baud command and the adapter baud command back-to-back
in the same TCP write, so the adapter forwards the Lumagen command at the old speed before
switching itself.

### Lumagen baud command

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

### USR-TCP232-302 baud command

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

### Power on/off messages

When the Lumagen powers on with echo enabled, it sends `Power-up complete.\r\n`.
When powering off (standby), it sends `POWER OFF.\r\n`.
These can be used as sentinels to confirm the operation completed.
