# MicroMusic · MiniLPC-HQ (ATtiny13A)

Experimental native-only eight-stage LPC speech codec for 1 KB ATtiny13A Flash. Clock **9.6 MHz** (CLKPR set to /1 by firmware), PWM PB1/OC0B at 37.5 kHz, speech sample rate 7.5 kHz. Current implementation is a proof of concept tested in a cycle-counting AVR emulator, **not tested on physical hardware**.

## Goal and verified results

All metrics calculated with `pystoi.stoi(original, decoded, fs_sig=7500, extended=False)` against the three provided prepared original recordings. Training and evaluation share the same clips; the numbers do **not** indicate quality on unseen speech. STOI measures intelligibility, not timbre identity.

| Phrase | Previous VBR2 STOI | MiniLPC-HQ STOI | Flash | Decoder code | Speech data |
|---|---:|---:|---:|---:|---:|
| Chego tebe nuzhno? | 0.781 | **0.852** | **887 B** | 412 B | 474 B |
| Chto zh ty ne otvechaesh? | 0.710 | **0.776** | **805 B** | 412 B | 392 B |
| Sova, otkryvai, medved prishel! | 0.800 | **0.824** | **1023 B** | 412 B | 610 B |

One final byte in each flash image terminates the speech loop; the **full Flash size** includes all code and data. EEPROM is not used. Each image fits ≤1024 B of Flash.

## What changed

* New **single format**: frames of **64 (8.53 ms), 128 (17.07 ms), or 256 (34.13 ms)** samples. `0x7F` acts as a new short-frame escape; `0xFF` marks the end of a repeating phrase. The AVR decoder supports only this native format, without legacy branches.
* Frame header stores pitch, four-bit gain, one of four voiced excitation shapes (or noise excitation), and the coefficient-update kind. Eight signed four-bit reflection coefficients can be sent in full, only K1–K4, only K5–K8, or reused.
* Offline **analysis by synthesis**: `train_hq.py` selects short frames, then `refine_hq.py` tunes pitch, gain, excitation profile and all eight LPC coefficients using the bit-exact model and STOI/spectral objectives.
* Timer0 output interrupt updates OCR0B; LPC math runs in the main loop. No floating point or multiply hardware required on AVR.

## Run / reproduce assembled binaries

Requirements: Python 3.11+ with NumPy, SciPy, Numba, soundfile and pystoi; `clang` with AVR target, `llvm-objcopy`, `llvm-objdump`; Node.js for the cycle-counting AVR verification.

```bash
python -m pip install -r requirements.txt
python build_hq.py
node verify.js
python make_player.py
node ui_smoke.js
```

The private archive includes original reference WAVs, baseline formant parameters, all three trained parameter sets, HEX/ASM and result PCM. Assembling these trained parameters produces **byte-identical** HEX files. Automated further training is optional and can change the result:

```bash
python train_hq.py --voice chego --seconds 45 --attempts 80
python refine_hq.py --voice chego --seconds 45
python build_hq.py
node verify.js
```

Optimization uses a time budget and may pick a different local optimum on different machines. For exact reproducibility use the included `samples/*/trained.npz` and only run `build_hq.py`.

The code-only archive intentionally contains neither the copyrighted speech recordings nor their encoded data, but includes a fully compiled **synthetic demo** HEX and the associated source. In the code-only archive, run `python build_demo.py && node demo_verify.js`. The full `run_all.sh` command needs the private reference and trained-parameter files.

## Web test page

`index.html` is self-contained and works without a server. Select a phrase and a playback source: original, the prior MiniLPC VBR2, LPX3 reference WAV, or the new ATtiny13A output. "Play" uses cached PCM produced by actual AVR execution; "Verify HEX" executes the instruction stream again in-browser and checks each audio sample, Timer0 overflow, timing and firmware size. WAVs can be downloaded directly if the browser cannot produce audio.

## Hardware

* CPU internal RC 9.6 MHz (firmware sets CLKPR /1). Configure oscillator/fuses as appropriate, verify with programmer; make sure supply voltage is sufficient per the ATtiny13A datasheet.
* Output PB1 / OC0B through a low-pass RC and an input-stage amplifier. Do **not** drive a loudspeaker directly from the pin.
* Software emulator cannot reproduce oscillator tolerances, analog PWM filtering, supply noise or speaker output.

## Copyright

The private archive contains user-supplied excerpted audio and is intended for individual experimentation. Do not publish these samples or derived LPC data openly without the necessary rights. The code-only archive contains no media excerpts.
