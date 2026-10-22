# MicroMusic — Keyframe LPC-8 for ATtiny13A

## What it does

Two real 1KB ATtiny13A speech firmware builds from the user's three voice experiments:

* `xtuj-ntt` — «Чего тебе нужно?»; Flash **1019 B** (184 B voice stream), 36 × 256 samples, 7500 Hz.
* `ne-otv` — «Что ж ты не отвечаешь?»; Flash **985 B** (150 B voice stream), 31 × 256 samples, 7500 Hz.

CPU internal 9.6 MHz (CPU divider /1), Fast PWM on PB1/OC0B at 37.5 kHz, Timer0 IRQ updates OCR0B every fifth overflow, a 16-byte ring buffer, and the main loop synthesizes eight-lattice-filtered speech. Output needs RC low-pass + audio amp; **do not attach a speaker directly to the GPIO**.

Unlike conventional frame-by-frame TinyLPC, *Keyframe LPC-8* uses two frame types:

- Full keyframe (6 B): 6-bit fundamental period, gain, eight 4-bit signed reflection coefficients; pitch header `0x00..0x3f`.
- Pitch/energy-only update (2 B): header `0x80..0xbf`, gain; keeps previously loaded spectrum.
- Silence run (1 B): `0xe1..0xfe` = 1–30 frames; `0xff` loops the stream.

The synthesis coefficients in SRAM are incremented/decremented at most one level every four audio samples (0.533 ms), and gain likewise; fundamental period already glides gently when the difference is small. The encoder chooses important spectral keyframes and tests synthesis against both the **source voice** and an **LPX3 teacher**, then adjusts stored parameters in an automatic greedy analysis-by-synthesis loop.

## Automated reproduction (private archive)

Dependencies: Python 3, `numpy scipy numba soundfile pystoi`, `node`, `clang` with AVR backend, `llvm-objcopy`, Chromium + Python Playwright for browser check. Python installation example: `python -m pip install -r requirements.txt`; install Playwright Chromium or point the test script at your system Chromium.

```bash
python run_all.py
```

This reconstructs `tinylpc.S` from the previous 8-stage base, selects keyframes in each sample, optimizes coefficients and F0/gain, builds Intel HEX, runs the AVR instruction interpreter, verifies **every emitted sample** against the Python model, produces comparison WAV and a standalone browser test page, and runs the UI test.

To optimize just one sample, e.g. with extra trials:

```bash
python train_keyframes.py --clip xtuj-ntt --skips 4 --budget 5000
```

Then build in that clip's folder and run `node verify.js` with `FRAMES=36` / `FRAMES=31`.

## Measured results

Calculated using `pystoi` on the supplied voice excerpts, relative to the prepared originals at 7500 Hz:

| Sample | Previous LPC-8 STOI | Keyframe LPC-8 STOI | Flash | Data | AVR/Numba disagreement | Missed Timer0 |
|---|---:|---:|---:|---:|---:|---:|
| «Чего тебе нужно?» | 0.7178 | 0.7222 | 1019 B | 184 B | 0/9216 samples | 0 |
| «Что ж ты не отвечаешь?» | 0.6199 | 0.6333 | 985 B | 150 B | 0/7936 samples | 0 |

These are objective, short-sample evaluations, not proof of human-perceived likeness. The significantly larger LPX3 codec remains more accurate to the original voice. **This does not match LPX3 quality within 1KB**; retaining LPX3-quality residual excitation would require vastly more storage or extra memory.

In emulation: 9.6 MHz, max 60 cycles per interrupt vs 256-cycle Timer0 period; no timing underruns. Unverified on a physical ATtiny13A. The chip has 64 B SRAM; the ring and filters plus stack remain inside bounds. Default factory clock divider is disabled in software and should also be checked in fuses; CPU needs suitable supply voltage.

## Browser audio

`release/index.html` or `MicroMusic_KeyframeLPC_ATtiny13.html` has embedded PCM, so it works offline. Playback is Web Audio started by user gesture, with explicit stop and volume buttons. The browser also runs the actual HEX in a time-aware AVR interpreter and compares each PWM update to the reference raw PCM.

## Copyright / publishing

`datasets/*` and `release/index.html` contain excerpts from copyrighted cartoons and/or derived voice data. The **private** archive is for personal experiments. The **code-only** archive intentionally excludes voices, LPX3 excerpts, generated speech bins, and the HTML with embedded clips. Respect the relevant rights before publishing media or ROM data in a public repo.
