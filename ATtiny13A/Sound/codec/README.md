# MicroMusic MiniLPC HQ4 — ATtiny13A speech experiments

## Results (confirmed from AVR HEX)

| Speech | HQ3 STOI | HQ4 balanced STOI | Flash size (code + voice) |
|---|---:|---:|---:|
| Chego tebe nuzhno? | 0.89484 | 0.90060 | 959 bytes |
| Chto zh ty ne otvechaesh? | 0.81619 | 0.81906 | 885 bytes |
| Sova! Otkryvay! Medved prishel! | 0.85518 | 0.85960 | 1024 bytes |

There is also an **HQ4 maximum-STOI** firmware for the first phrase: **0.90182 STOI, 957 bytes Flash**. Its spectral-envelope mismatch is higher than the balanced version, so both versions are preserved. HTML lets you hear both.

The ATtiny13A decoder occupies **406 bytes**, including vectors and startup, and uses a signed 8-stage LPC lattice with four excitation profiles. F_CPU = 9.6 MHz (CKDIV8 disabled by software), Fast PWM 37.5 kHz via PB1/OC0B, 7.5 kHz sample rate. EEPROM is not required.

Measured against the supplied recordings: 39,424 total output samples, 0 differences between exact numerical model and the assembled AVR interpreter, 0 missed Timer0 overflow events. Maximum ISR 28 CPU cycles. Tested digitally only, NOT on the physical microcontroller. STOI measures intelligibility, not identity/naturalness of voice.

## Files

- `MicroMusic_MiniLPC_HQ4.html` or `release/index.html`: offline Web Audio player, real AVR interpreter for verification and comparison (original / HQ3 / HQ4 balanced / HQ4 max / LPX3).
- `release/<clip>/firmware.hex`, `firmware.bin`, `firmware.S`, `speech.hq`: three actual AVR variants with compressed speech.
- `release/chego_stoi_max/`: first phrase, highest STOI variant.
- `release/<clip>/AB.wav`: RMS-leveled original, HQ3, original, HQ4 balanced, LPX3 comparison.
- `trained/<clip>/best.npz`: quantized LPC frames and frame lengths, saved after optimization.
- `optimize_hq4.py`: feedback encoder, frame parameter optimization with total Flash and click limits.
- `refine_boundaries.py`: optimized frame boundaries (64/128/192/256 audio samples per frame).
- `refine_timbre.py`: optimize spectral-envelope error while respecting a minimum STOI.
- `convert_audio.py`: MP3/WAV to normalized mono WAV preprocessing (check `--help`).
- `build_hq4.py`: assembler, PCM model verification, creates HEX/PCM/WAV/report and invokes `verify_hq4.js`.
- `make_player_hq4.py`: produces standalone HTML player with embedded files.
- `hq4_core.py`, `model.py`, `verify_hq4.js`: exact arithmetic model and cycle-based AVR emulator.

## Rebuild, verify and train

Requirements: Python 3 with `pip install -r requirements.txt`, `clang -target avr`, `llvm-objcopy`, Node.js.

```bash
python build_hq4.py
python make_player_hq4.py
```

The scripts reproduce the **balanced** three firmware images. After copying this project anywhere, the full private archive includes all reference WAV and training parameters.

Run a new parameter search, then regenerate all binaries:

```bash
python optimize_hq4.py --clip chego --seconds 60 --seed 42
python refine_boundaries.py --clip chego --passes 8
python refine_timbre.py --clip chego --floor 0.900 --seconds 30
python build_hq4.py
python make_player_hq4.py
```

Optimization searches are explicitly best-effort. If no better values are found, the preserved `trained` snapshots remain reproducible. Keep a backup before running the optional retraining commands.

## Intellectual property

The original film excerpts and speech-derived firmware are included **solely for private evaluation**. Do not publish those recordings or their derived speech data to a public GitHub repository without appropriate rights. The audio-free code archive is separately provided for source review; it is not by itself a complete training dataset.
