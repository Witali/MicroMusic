# MicroMusic — Adaptive Keyframe LPC-8 for ATtiny13A

Two short spoken-phrase firmware builds, each fitting in **1024 bytes of Flash total**, using an eight-stage LPC lattice and keyframed spectral parameters. Builds are intended for **ATtiny13A** running its internal RC at **9.6 MHz**, no /8 divider. Audio is **7,500 samples/s** as PWM duty-cycle updates at **37,500 Hz** through **PB1/OC0B**. The 16-byte ring buffer lives in the 64-byte SRAM; main loop synthesizes speech; an interrupt drains the buffer.

## What's new vs Keyframe LPC-8 v1

The decoder now supports **per-frame variable slew speed** for all eight reflection coefficients and gain:

- `fast=1`: one quantized step every **4 PCM samples** (~0.53 ms)
- `fast=0`: one quantized step every **8 PCM samples** (~1.07 ms)

The encoder evaluates speech frames in context using a bit-exact synthesis model, chooses fast/slow individually, selects spectral keyframes under the Flash cap, and runs an analysis-by-synthesis random coordinate refinement over pitch, gain and reflection coefficients. This reduces spectral-edge discontinuities while retaining a gradual vowel envelope. **Pitch already has its own separate conditional glide, one step per 8 samples.** This version does not yet have LPC2's 10-stage filter, full residual or precise formant postfilter.

**Bitstream**: Bit 6 of the frame pitch header now means `fast`. It was previously unused: no extra voice-data bytes for adaptive speed. Bit 7 still indicates a short pitch/gain-only event (reuse previous spectral targets). For full keyframe the header has bit7=0 and the same four coefficient bytes plus energy nibble, plus final low-nibble coefficient byte as before. High headers `0xE1..0xFE` encode runs of 1–30 silent frames and `0xFF` loops. **Pitch periods in the adaptive streams are <=31** to avoid short-record collisions with silence opcodes. Each frame lasts 256 samples (~34.13 ms).

## Measured results

Measured on two supplied recordings with the source-aligned STOI metric. These are offline simulation results, **not physical-chip or subjective human-listening tests**.

| Sample | Previous STOI | New STOI | Full LPX3 reference STOI | Flash size incl. data | Speech stream | AVR/Numba mismatches |
|---|---:|---:|---:|---:|---:|---:|
| Чего тебе нужно? | 0.7222 | **0.7366** | 0.8030 | 1023 / 1024 B | 180 B | 0 / 9216 |
| Что ж ты не отвечаешь? | 0.6333 | **0.6457** | 0.7667 | 997 / 1024 B | 154 B | 0 / 7936 |

Both use an AVR interrupt on every Timer0 overflow (37.5 kHz), and update `OCR0B` every fifth overflow. Cycle-counting emulation shows 0 missed timer overflows and 0 audio underruns; maximum IRQ cost 60 cycles, under the 256-cycle PWM period. Simulation is not a substitute for checking the RC oscillator and supply voltage on real hardware.

**Caveat:** STOI indicates intelligibility, not faithful preservation of individual speaker identity. For the first phrase, a tradeoff remains: the new version has higher STOI, but the spectral error to the original rises slightly compared to v1 (0.8885 to 0.8940 in this project's weighted-band metric). The second phrase's spectral error remains essentially unchanged (0.9568 to 0.9573). LPX3 is still substantially closer to the source voice.

## Files

- `tinylpc.S` — tested AVR assembly; includes the per-frame bit-6 adaptive mode.
- `build_firmware.py`, `avr_emulator.js`, `verify.js` — firmware build and cycle-accurate PCM check.
- `model_adaptive.py`, `package_adaptive.py`, `train_adaptive.py` — exact Python model, bit packing, automatic pitch/energy/LPC optimization and speed flag selection.
- `run_all_adaptive.py` — run everything automatically and rebuild both HEXes and browser page.
- `make_adaptive_demo.py`, `test_adaptive_browser.py` — standalone HTML player and automated Chromium/Web Audio checks.
- `adaptive_results/*/tinylpc.hex` — ready-to-test Intel HEX per phrase.
- `release/index.html` — offline browser A/B player including original, LPX3, old Keyframe and new Adaptive; its verification button re-executes the embedded HEX.
- `release/*_AB.wav` — direct comparison files, with equally filtered/volume-balanced tracks.

## Reproduce

Requires Python 3, `numpy`, `scipy`, `numba`, `pystoi`, `soundfile`, and also `clang` with AVR backend, `llvm-objcopy`, `node` and Chromium with Python `playwright`.

```bash
pip install -r requirements.txt
python run_all_adaptive.py
```

Train just one phrase with another search budget:

```bash
python train_adaptive.py --clip xtuj-ntt --budget 4000
```

For hardware: first check low fuse / clock, avoid disabling ISP RESET/SPIEN. PB1 must feed a low-pass filter and audio amplifier, **not a speaker directly**. Never flash code based solely on simulation without electrical/clock verification.

## Source audio / copyright

This private archive includes voice samples from third-party cartoons for private study. The `code_only` archive excludes original audio, LPX3 reference samples, speech data, generated voice HEX and any HTML with embedded copyrighted material. Permission may be required before publishing the voice samples or derivative encoded audio online. The code is not a license to redistribute them.
