# MicroMusic · MiniLPC8 PulseProfiles New-only

**Experimental firmware for ATtiny13A, 1 KiB Flash, 64 B SRAM, 64 B EEPROM.**

One and only one on-chip bitstream format is supported. Legacy Full 350 and LPX3 appear **only in the private HTML comparison player**, never in firmware. This branch is the optimized version of the four-excitation-profile experiment.

## New bitstream layout

Each frame lasts **256 audio samples** at **7,500 samples/s** (about 34.1 ms) and occupies **six bytes**:

- Byte 0: pitch period (0 = unvoiced/noise).
- Byte 1: bits 0–3 = gain (0–15); bits 4–5 = excitation profile (0–3). Bits 6–7 reserved (must be zero).
- Bytes 2–5: 8 signed four-bit LPC reflection coefficients, each nibble decoded as `k = nibble - 8`.

The decoder runs an 8-stage fixed-point lattice filter and uses the high nibble **directly** to change two middle taps of the 4-sample excitation pulse. It does *not* decode historical byte layouts.

Pulse amplitudes (in gain units) for the four profile IDs:

| ID | Voice pulse (relative amplitude) |
|---|---|
| 0 | [2, 3, 2, -1] |
| 1 | [2, 2, 2, -1] |
| 2 | [2, 3, 1, -1] |
| 3 | [2, 2, 1, -1] |

Note that the 4 sample values are the excitation *before* the LPC filter. Unvoiced sound uses a small LFSR noise generator.

## Size

| Example | Decoder / initialization / ISR | Speech | End marker | Full image |
|---|---:|---:|---:|---:|
| Chego | 364 B | 216 B | 1 B | **581 B** |
| Otvechaesh | 364 B | 186 B | 1 B | **551 B** |
| Vinni | 364 B | 522 B | 1 B | **887 B** |

The previous compatible-profile prototype had 368 bytes before data, so moving to the single new format saves **4 bytes**; the old 350-byte Full had no profile feature and was smaller, but less flexible. We have not gained 18 bytes by dropping a legacy decoder: the feature itself is responsible for most overhead.

## Build, run, verify

Requires `clang` with AVR backend, `llvm-objcopy`, Node.js, Python 3.

```sh
python3 build.py
node verify.js
```

`verify.js` executes the **compiled AVR program** with a cycle-counting interpreter; it compares every output sample with the mathematical reference, checks Timer0 overflows and deadlines. Verified: 0 mismatches across 39,424 samples, 0 missed overflows, maximum ISR 28 cycles. This is not a real-hardware test.

The HTML `index.html` is entirely self-contained and offers A/B comparison with original voices, LPX3 and Full 350, plus a new-only firmware verification button. The reference voices are copyrighted and are included for **private evaluation**, not publication. To rebuild the HTML within this private package:

```sh
python3 make_player.py
```

To experiment with automatic selection of the two profile bits (requires `numpy`, `numba`, `soundfile`, `pystoi`):

```sh
python3 train_profiles.py --voice chego --apply
python3 build.py
node verify.js
python3 make_player.py
```

## Hardware

- Clock: 9.6 MHz internal RC, code sets CLKPR divider to /1.
- Fast PWM: 37.5 kHz, output PB1/OC0B.
- New audio sample every five Timer0 overflows (7.5 kHz).
- Use a low-pass output filter and a suitable amplifier; do not drive a speaker directly from PB1.
- Not yet verified on a physical ATtiny13A.

## Publishing

For a public GitHub repository, remove original WAVs, LPX3 derived streams, user-provided cartoon audio, and any derivative LPC speech data or firmware embedding it unless permissions allow redistribution.
