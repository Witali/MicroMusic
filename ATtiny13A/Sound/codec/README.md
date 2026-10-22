# MicroMusic — MiniLPC HQ4 (controlled experiments)

## Goal

Explore closer reproduction of three supplied voice clips while keeping **the whole actual AVR firmware** (decoder + encoded voice + terminator) inside ATtiny13A's **1024 bytes of Flash**, at CPU 9.6 MHz. The code uses 8 lattice LPC stages, 7,500 PCM samples/s, a 37.5 kHz Fast PWM carrier on PB1/OC0B and no floating-point math. Only one VBR frame format is supported. All versions use **406 bytes of decoder code**; there is no legacy compatibility branch.

### Findings (October 21, 2026)

All numbers below are measured with the **same** canonical source WAV and `pystoi` (not subjective listening scores). Smaller logarithmic spectral distance is better. These are *training-set recordings*; the values do not predict performance on new speech.

| Voice | Variant | STOI ↑ | Spectral error ↓ | Flash bytes |
|---|---|---:|---:|---:|
| Chego | HQ3 | 0.894838 | 1.36688 | 947 |
| Chego | HQ4 intelligibility | 0.894928 | 1.36947 | 951 |
| Chego | HQ4 timbre | 0.891950 | 1.35059 | 959 |
| Otvechaesh | HQ3 | 0.816194 | 1.24683 | 878 |
| Otvechaesh | HQ4 intelligibility | 0.816431 | 1.26585 | 882 |
| Otvechaesh | HQ4 timbre | 0.814196 | 1.23088 | 880 |
| Vinni | HQ3 | 0.855178 | 0.94783 | 1007 |
| Vinni | HQ4 intelligibility | 0.855178 | 0.94783 | 1007 |
| Vinni | HQ4 timbre | 0.855042 | 0.93795 | 1023 |

**Interpretation:** This is **not** a breakthrough. The tiny STOI gains are not meaningful on their own. The separate spectral variant reduced the chosen spectral error by approximately 1% but can slightly lower STOI. No variant reached 0.900 STOI. Do an A/B hearing test; a spectral distance is not proof of increased likeness to an actor.

The explored ideas included:
* Joint and annealed frame parameter search, optional frame splitting and extra 64-sample frames.
* Several alternative excitation pulse shapes using the existing two mode bits.
* Three alternate unvoiced/noise patterns for consonants.
* Wider coefficient scale (Q3 versus Q4) with bit-exact fixed-point experiments.
* Constraint on abrupt changes of at least 48 unsigned-PCM levels.

**None of the pulse/noise/Q3 modifications improved the result on all three recordings**, so no unnecessary AVR instructions were added. Code is identical across all tested variants; only compressed voice parameters differ.

## Verification

From actual assembled AVR instructions executed in `avr_emulator.js`:
* 9 variants = 3 clips × 3 configurations.
* **0 mismatches** versus the 8-bit PCM from the exact numerical model on every one of the 118,272 processed audio sample instances (three profiles × 39,424 samples).
* **0 missed Timer0 overflows**, **0 irregular PWM update intervals**.
* Max ISR duration **28 CPU cycles**, stack depth 4 in the emulator.
* All nine actual HEX files at or below 1024 bytes Flash.

This is **software emulation**, not physical AVR verification. Hardware clock, output filtering, voltage, and amplifier can alter the resulting sound.

## Reproduction

Install a recent Python 3, the requirements in `requirements.txt`, `clang` with AVR target, `llvm-objcopy` and Node.js. From the project directory:

```bash
python build_hq4.py
node verify_hq4.js
python make_player.py
```

Outputs live in `release/<phrase>/<variant>/`: `firmware.S`, `firmware.bin`, `firmware.hex`, `speech.hq`, `pcm.u8`, `preview.wav`. `release/report.csv`, `release/verification.json`, `release/index.html` are summary outputs.

### Closed-loop optimisation

To rerun a saved, reproducible search starting from HQ3 streams:

```bash
python optimize_hq4.py --phrase chego --max-trials 4000 --seed 1437
python refine_timbre.py --phrase chego --passes 2 --min-stoi-drop 0.001
```

Candidates are **not silently accepted**. The code enforces the Flash limit and tests the quantized 8-bit synthesizer output, with a guard against large sample-to-sample jumps. Experiment scripts save frame arrays, parameters, the RNG seed and a JSON report. `anneal_hq4.py`, `pulse_experiment.py`, `noise_experiment.py` and `coeff_scale_experiment.py` retain negative experiments too. Save their outputs separately when exploring so as not to overwrite selected releases.

**Input preprocessing**: `convert_audio.py` prepares MP3 or WAV. The canonical `references/<name>/original.wav` files are the snapshots used for the reported metrics. The archived source MP3 and canonical preprocessed references are not guaranteed to produce bit-identical output when newly processed with different ffmpeg builds or normalisation settings.

### Code-only public demo

`python demo_synthetic.py` creates and builds an independent, synthetic phrase-like test using the real decoder. No movie audio or trained speech parameters are required for that demo. The code-only ZIP deliberately does **not** include cartoon recordings, any trained samples or other derivatives of third-party audio.

## Distribution

The **private** archive contains samples supplied for individual evaluation, including copyrighted animated-film dialogue. Do not publish those recordings or derivative voice data in a public repository without appropriate permissions. The code-only archive contains the reusable algorithms and one synthetic example.
