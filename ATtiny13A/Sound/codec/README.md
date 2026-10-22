# MicroMusic: MiniLPC-HQ3 DecoderOpt (ATtiny13A)

This experiment optimizes **only the AVR decoder**. The LPC speech data and integer output are unchanged.

## Target

- ATtiny13A: 1024 B Flash, 64 B SRAM, 64 B EEPROM (EEPROM is not used here)
- Internal 9.6 MHz clock, divide-by-8 disabled
- Fast PWM 37.5 kHz on PB1/OC0B; audio duty-cycle updates at 7500 Hz
- 8-stage signed LPC filter and four excitation profiles; one VBR speech format

## Verified results

| Phrase | Baseline Flash | Optimized Flash | PCM values checked |
|---|---:|---:|---:|
| chego | 947 B | 929 B | 9216 |
| otvechaesh | 878 B | 860 B | 7936 |
| vinni | 1007 B | 989 B | 22272 |

- **Machine code area: 406 -> 388 B**, including vectors, reset, filter, frame parser, multiply and ISR.
- **Max modeled ISR: 28 -> 19 CPU cycles** (interrupt entry accounting is part of the cycle-counting emulator's `maxISR` metric).
- **0 output PCM mismatches** across all 39,424 samples compared with the unmodified HQ3 AVR implementation.
- All three streams: matching Timer0 IRQ counts, 0 missed overflows, and 2 vs 4 bytes of modeled stack use.
- No change to learned LPC parameters; quality metrics (e.g. STOI and timbre) are exactly unchanged.

## Source changes

1. Reserve register `r11` for the constant PWM countdown reload `5` and `r12` for SREG backup inside the ISR. This avoids PUSH/POP of the temporary registers; **do not use r11/r12 in the foreground** without updating the ISR.
2. Initialize XH (`r27`) and YH (`r29`) once; neither pointer can cross page `0x00xx` in this program. Remove redundant high-register clears from the hot loops.
3. Decode two packed signed 4-bit coefficients via `r16` and `r17` without an extra register copy.
4. Share the pointer/counter setup across the four variable-length frame types.
5. Retain the original signed 8-bit multiply behavior and all VBR bitstream values.

The shorter Flash binaries require changing `VOICE_ADDR` from `0x196` (406) to **`0x184` (388)**. This is already done in each firmware.S. Voice data is stored immediately after the code rather than leaving padding bytes.

## Rebuild & verify

Requires `clang` with AVR target, `llvm-objcopy`, `readelf`, `node`, and Python 3:

```
python3 build_and_verify.py
python3 make_player.py
python3 browser_test.py     # optional: requires Playwright and system Chromium
```

All three voice subfolders include `firmware.S`, `speech.hq`, `firmware.bin`, `firmware.hex`, `firmware.sha256`, and `reference.bin`. `verify.js` executes the true instruction stream and produces `report.json` and `emulated.pcm`.

`index.html` is fully offline. The Play button uses the **precomputed output of the AVR emulator** for immediate sound; the “Исполнить HEX” button separately executes the actual embedded firmware in the browser and independently checks every sample. This is a digital emulation, not a physical ATtiny13A verification.

## Copyright / sharing

The private ZIP includes encoded speech derived from user-provided excerpts of commercial cartoons; do not redistribute those assets without appropriate rights. A separate code-only ZIP supplies an original synthetic test stream.
