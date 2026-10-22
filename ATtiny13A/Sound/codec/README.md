# MicroMusic — automatic LPC2 Improved → TinyLPC / ATtiny13A

**Experiment:** using a full LPC2 Improved vocoder as an *offline teacher* for a
small, fixed-phrase, 7-stage AVR lattice synthesizer, with automated
analysis-by-synthesis and byte-accurate verification of the compiled HEX.

The recorded sample in `references/` is the user-provided voice from the
animated film, intended **only for private testing**. Do not publish those
recordings, derived speech data, or the full archive without an appropriate
license/permission. The generic source-code algorithms are separate from the
example sound.

## Quick start — no manual coefficient tweaking

Dependencies: Python 3.11+, packages in `requirements.txt`, Node.js 20+, LLVM
Clang with AVR backend, `llvm-objcopy`, FFmpeg, and Chromium/Playwright.
In a Linux shell (or Windows 11 with WSL and the same packages):

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python run_all.py --budget 2500 --presets balanced
```

This processes the included *private reference recording*, automatically:

1. Re-encodes **LPC2 Improved v11** in headless Chromium using the actual
   saved HTML implementation, then decodes it as a quality/timbre reference.
2. Loads initial quantized AVR parameters for this phrase.
3. Proposes random coordinate edits to per-frame reflection coefficients
   `K0..K6` (4-bit), pitch period `P` and gain `E`.
4. Synthesizes each candidate in a **byte-exact** model of the AVR fixed-point
   code (verified against the 22,272 samples from the original AVR emulator).
5. Scores the result against **both** the original and LPC2 Improved spectra,
   as well as STOI, loudness envelope and large one-sample discontinuities.
   Candidates that regress protected metrics are rejected; seed and budget make
   the search reproducible.
6. Packs silence RLE and speech data, assembles genuine Intel HEX, checks
   Flash <= 1024 bytes, and independently executes the HEX with a JavaScript
   AVR instruction emulator, checking timing and **every output sample**.
7. Writes `results/current/index.html`, `optimized_avr.wav`,
   `AB_comparison.wav`, `optimized.hex` and `report.json`.

More extensive automated comparison:

```bash
python run_all.py --budget 2500 --presets balanced,voice,lpc2
```

The pipeline picks the best acceptable profile under explicit final guards:
STOI no worse than baseline by 0.0002, original spectral distance no worse,
no increase in the large step/click counts. This is a guard on **these**
measurements, **not** proof of identical subjective sound quality.

To repackage a previously optimized checkpoint without spending CPU time on
another search:

```bash
python run_all.py --presets '' \
  --candidate results/balanced/optimized_parameters.npz
```

To prepare and encode a different sound automatically:

```bash
python run_all.py --input path/to/speech.mp3 --budget 2000
```

The script automatically detects speech boundaries, resamples to 7500 Hz,
encodes LPC2 Improved at 8000 Hz, creates initial LPC-7 parameters, and runs
search/verification. **A new recording may exceed 1 KB Flash**, even after
silence compression. If it does, build will stop with an explicit error rather
than truncating speech. You may supply `--trim 0.2:2.9` if automatic silence
trimming needs adjustment. You can supply a separately produced LPC2 teacher
with `--teacher-wav path/to/teacher.wav`.

## Verified result on the included phrase

| Metric | Initial LPC2-Lite | Auto-trained | Direction |
|---|---:|---:|---|
| STOI | 0.777951 | 0.778630 | ↑ |
| 24-band spectral error vs original | 0.522779 | 0.510501 | ↓ |
| 24-band spectral error vs LPC2 | 0.609774 | 0.584742 | ↓ |
| Large step count ≥48 | 9 | 0 | ↓ |
| Maximum PCM step | 54 | 47 | ↓ |
| Program Flash | 1012 | 1012 bytes | ≤1024 |
| Compressed voice stream | 343 | 343 bytes | — |

The compiled program yielded **22,272 identical samples** between the optimized
mathematical model and the independent instruction interpreter, with
**111,360 Timer0 interrupts, 0 missed**, a worst ISR length of 60 CPU cycles,
max stack depth 8 bytes, and no measured audio-buffer underflows.

*These are digital simulation results. The firmware has not been tested on
physical ATtiny13A. The CPU is 9.6 MHz; output is PB1/OC0B Fast PWM at
37.5 kHz and audio samples at 7.5 kHz. Low-pass filtering and an amplifier
are necessary for a real loudspeaker.*

## Architecture and what is (not) ported

Full LPC2 Improved uses 10 LPC coefficients from LSF, frame/subframe
interpolation, transient/mixed excitation, a post-filter, and a wider sample
format. **That full decoder does not fit our current ATtiny13A implementation.**

We have *transferred LPC2 Improved's spectral goal to the encoder*. Heavy
optimization runs on a PC and creates a compact custom TinyLPC parameter
stream. On the ATtiny13A, the familiar 7-stage reflection filter and cheap
four-sample glottal excitation remain. Consequently the codec is **not**
bitstream-compatible with LPC2 and does not offer transparent LPC2-quality
reconstruction. For a faithful LPC2 decoder use a bigger MCU or external
memory, rather than silently pretending no quality has been lost.

The auto-trained variant does not modify AVR code (the improvement is in the
encoded quantized coefficient stream), which is why executable size stays
at 1012 bytes. It is reproducible via optimization seed 2026 and budget 2500.

## Directory guide

- `generate_lpc2_teacher.py`, `lpc2_improved_encoder.html`: LPC2 Improved
  encoder and decoder run automatically in headless Chromium.
- `prepare_source.py`, `generate_seed.py`: prepare and fit any short input.
- `model_lite.py`: byte-exact signed wraparound AVR synthesis mathematics.
- `perceptual.py`: multi-reference evaluation and objective functions.
- `optimize.py`: iterative, reproducible analysis-by-synthesis search.
- `run_all.py`: full end-to-end one-command orchestration.
- `firmware/tinylpc.S`, `build_firmware.py`, `package_stream.py`,
  `avr_emulator.js`, `verify.js`: actual firmware and independent verification.
- `references/`: **private** source voice, initial parameters, LPC2 baseline.
- `results/release/`: checked binaries, scores, rendered waveform and
  standalone browser A/B player.

## Important constraints

- AVR SRAM is only 64 bytes; speech output uses a 16-byte ring buffer and
  8-bit lattice states. Quantization and clipping can cause audible changes
  not captured by spectral objectives.
- A 7.5-kHz sample rate cannot reproduce high-frequency consonants above
  3.75 kHz; no encoder objective can restore information that does not exist.
- Automatic spectral fitting of a single sentence may not generalize to a
  different voice or sentence. Always re-encode and compare each sample.
- Optional copyright-restricted demonstration audio must be removed from a
  public GitHub release.
