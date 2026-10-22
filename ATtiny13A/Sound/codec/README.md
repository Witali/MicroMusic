# MicroMusic — multi-phrase TinyLPC / ATtiny13A

Closed-loop experimental encoder; tests two distinct user-provided audio clips. **LPC2 Improved is a high-quality reference/teacher**, while the compiled AVR uses the smaller 7-stage TinyLPC model (it is not a compatible or full-quality LPC2 bitstream).

## Quick start

Install Python dependencies: `numpy scipy soundfile numba pystoi playwright`, plus `ffmpeg`, `clang` supporting `-target avr`, `llvm-objcopy`, `node` and Chromium. Install Playwright's Chromium if your system has no Chromium binary.

Run with supplied example MP3s from the private archive:

```bash
python run_multi.py --clip xtuj-ntt=inputs/xtuj-ntt.mp3 --clip ne-otv=inputs/ne-otv.mp3 --budget 1200 --refine 3000
```

Each clip is handled independently: convert to 7.5 kHz mono with VAD trimming; generate LPC2 Improved teacher with the saved real JS codec running under Chromium; estimate quantized LPC coefficients; refine using analysis-by-synthesis with STOI and spectral goals and click limits; encode silence with RLE; compile real ATtiny13 AVR firmware; execute real Intel HEX instructions with the included JavaScript AVR emulator; byte-compare all output PCM samples to the Python model; create WAV, A/B sample, metrics and self-contained player.

The website uses Web Audio API activated by explicit user tap instead of large `data:audio` links, and includes separate WAV files for phones where the in-app viewer doesn't enable audio. Open `release/index.html` in an actual mobile browser.

**Hardware:** ATtiny13A 9.6 MHz (disable CKDIV8), Fast PWM 37.5 kHz on PB1/OC0B and 7.5 kHz audio. Requires RC low-pass and amplifier; only digital emulation was tested. Current machine code is fixed for a limited seven-stage 8-bit filter; long phrases may exceed 1024 B, and the script fails rather than truncates.

**Copyright:** Uploaded cartoon audio and derived speech data are included only in the **private** archive. Do not publish the private files or example firmware without clearing rights. `code_only.zip` does not include the original voice recordings or encoded speech data.

## LPC-7 versus LPC-8

The optional **8-pole format** adds one quantized coefficient (one extra byte per voiced frame) and one extra SRAM state. The new AVR firmware and matching exact Python model (`format8/tinylpc.S`, `model8.py`, `optimize8.py`) are automatically built, trained and tested alongside the established 7-pole format. It is **not** the full 10-pole LPC2 Improved.

The separately tested 4/8/12/16-entry formant codebook format saved speech-data bytes but degraded STOI substantially on these two clips, so the default release preserves per-frame coefficients. The comparison is in `codebook_trial_report.json`.
