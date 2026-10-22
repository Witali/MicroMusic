# MicroMusic · MiniLPC-HQ4 · ATtiny13A

Three independent speech firmware examples for the ATtiny13A (1 KiB Flash, 64 B SRAM, 9.6 MHz clock, Fast PWM OC0B/PB1 37.5 kHz, PCM 7.5 kHz). A single shared **406-byte** AVR decoder with an eight-stage integer LPC lattice; no compatibility code for older bitstreams.

| Phrase | STOI, HQ3 | STOI, HQ4 | Flash bytes | Speech bytes |
|---|---:|---:|---:|---:|
| Чего тебе нужно? | 0.894838 | 0.894923 | 949 | 542 |
| Что ж ты не отвечаешь? | 0.816194 | 0.816292 | 878 | 471 |
| Сова! Открывай! Медведь пришёл! | 0.855178 | 0.855543 | 1023 | 616 |

The quality improvements in this conservative release are **small**. They are verified against the **exact reference WAV files** stored under `MicroMusic_HQ3_Verified_Release` rather than inferred from listening. Subjective voice similarity has not been established to have improved. STOI is an intelligibility metric, not a timbre metric.

## How to verify

```bash
python3 rebuild_frozen.py
```

Requires Python + NumPy, Numba, SciPy, PySTOI, SoundFile; AVR-capable Clang/LLVM, Node.js. This recompiles the stored AVR assembly and checks the **entire Flash binary** against the release. Node's cycle-counting AVR interpreter checks every outgoing audio sample and Timer0 overflows.

## How to continue optimizing

```bash
python3 refine_and_build.py --seconds 30
```

This is an automated closed-loop randomized coordinate search over 8 LPC coefficients, pitch, gain and 4 excitation modes. It builds three new ROMs and writes results to `HQ4/`. Run `node verify_hq4.js` after each experiment. The number of trials is limited by wall time, so replaying the search is not guaranteed to rediscover exactly the same result; **rebuild_frozen.py** instead reproduces the released result exactly using the frozen `.npz` snapshots.

Source conversion script: `MicroMusic_MiniLPC_HQ2/convert_audio.py`, which takes arbitrary WAV/MP3 to fixed-rate canonical mono WAV with optional explicit alignment. The three immutable test reference WAVs are bundled for private A/B comparison. The source-only package excludes commercial cartoon audio and voice-dependent firmware.

**Hardware:** PB1/OC0B feeds an RC low-pass filter and high-impedance amplifier input; do **not** connect a speaker directly to the MCU pin. For 9.6 MHz operation CKDIV8 must be disabled or CLKPR configured for divide-by-1. Tests above were performed by emulation, not physical hardware.
