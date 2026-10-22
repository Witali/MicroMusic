# MicroMusic / ATtiny13A TinyLPC v2

Speech experiment: **«Сова, открывай! Медведь пришёл!»**

TinyLPC v2 is a runnable **981-byte AVR firmware (including 420 bytes of speech data)** for ATtiny13A (1024 bytes Flash, 64 bytes SRAM). It can be listened to in a standalone `index.html`, where a JavaScript interpreter executes the **actual AVR HEX instructions**, including Timer0 interrupts and writes to OCR0B. No audio samples from a premixed WAV substitute for the AVR code in this mode.

**Reference is the eSpeak-generated Russian speech in `tts_source.wav` — not the actor's original cartoon voice.** Fidelity scores below are measured relative to this synthetic reference. To optimize for an actual cartoon excerpt, supply an audio sample of that excerpt.

## What changed since v1

| | v1 | v2 |
|---|---:|---:|
| Flash (program + speech) | 917 B | **981 B** |
| Speech stream | 420 B | **420 B** |
| LPC reflection coefficients | 6 | **7** |
| Input frame / parameters | 256 samples, 34.13ms | 256 samples, 34.13ms |
| Voiced excitation | One impulse `[2]` | **Four-position chirp `[5,3,0,-2]`** |
| Unvoiced excitation | 8-bit LFSR | 8-bit LFSR |
| LPC coefficient analysis | 6th-order, preemphasized | 7th-order, raw source |
| Pitch/voicing decision | Loose threshold ~0.40 | More selective ~0.65 |
| STOI score* | 0.507 | **0.700** |

*STOI is a **short-time objective intelligibility** metric, not a measure of speaker identity or pleasantness. The values are for this **single 2.85 s synthetic test phrase** at 7500 Hz, using the AVR-emulator-generated output. The scores should not be interpreted as a general speech benchmark.*

The seventh reflection coefficient uses the previously unused high nibble of the fifth byte. Thus the amount of speech data **does not increase**. Improving the excitation shape also gives a large benefit without a chirp ROM table.

## Memory and PWM

- ATtiny13A, internal RC clock **9,600,000 Hz** (software selects clock divider /1).
- Timer0 Fast PWM @ **37,500 Hz**, OC0B/PB1 (physical DIP8 pin 6).
- Interrupt every 256 CPU cycles; one new **7500 Hz** PCM value is written on every fifth overflow.
- Main loop decodes frames, drives a seven-stage fixed-point lattice filter, and writes 8-bit samples to a **16-byte SRAM ring**.
- The ISR consumes buffered samples and writes `OCR0B` (saved registers and SREG).
- Coefficients are quantized to signed `-7..7`, multiplied by repeated addition and an arithmetic shift of three (no hardware multiplier).
- Speech: 84 frames × 5 bytes = **420 B** for 2.8672 s (including padded last frame).

### Actual AVR-emulator verification

Run `node verify.js` after `python3 build_firmware.py`:

- Flash image: **981 / 1024 B**.
- Ring buffer: **16 B**.
- Samples simulated: **21,504**.
- Timer0 ISR: **107,520** calls.
- Longest ISR: **60 cycles** (of 256).
- Timer overflows missed: **0**.
- Detected PCM buffer underruns: **0**.
- Maximum interval between consecutive PCM writes: **1281 CPU cycles** (nominal 1280, depending on instruction completion).

These checks are performed in the software model; the firmware has **not** been measured on physical hardware.

## A/B browser demonstration

Open `index.html`. All code, speech, and embedded comparison audio are included in this single HTML file. Five buttons:

1. `TinyLPC v2` — the new **981 B real AVR HEX** simulated instruction-by-instruction.
2. `TinyLPC v1` — previous **917 B real AVR HEX** simulated the same way.
3. `LPC2 Improved` — the more sophisticated PC JavaScript decoder from Audio Codec Lab (does *not* run on ATtiny13A).
4. `LPC1` — older JavaScript speech decoder (does *not* run on ATtiny13A).
5. `Исходная речь (TTS)` — uncompressed speech reference before LPC encoding, provided as an MP3 embedded in the page.

Track loudness is normalized for a fair comparison. You can also download the AVR HEX, speech stream, and AVR-emulated WAV from the page.

## Files

- `tinylpc.S` — bare-metal AVR assembly with 7-pole lattice and glottal chirp.
- `tinylpc.hex`, `tinylpc.bin` — firmware including speech.
- `tinylpc_v1.hex` — original firmware for A/B comparison.
- `voice_tinylpc.bin` — 420 bytes of new packed LPC frames.
- `make_tinylpc.py` — source analysis and speech parameter compression.
- `build_firmware.py` — assemble and export ROM (Clang AVR backend + LLVM objcopy required).
- `avr_emulator.js`, `verify.js` — timing-aware subset AVR interpreter and regression test.
- `index.html`, `page_template.html`, `create_page.py` — browser listening lab.
- `tts_source.wav`, `tts_source.mp3` — generated test utterance (not original cartoon recording).
- `lpc_math.js`, `phrase_lpc1.lpc`, `phrase_lpc2.lp2` — older LPC codecs/streams for comparison.
- `MicroMusic_TinyLPC_v2_preview.wav` — audible WAV rendered from the AVR HEX (with approximate analog output filters).
- `MicroMusic_TinyLPC_v1_preview.wav` — same for the v1 firmware.

## Rebuild

From this directory, with Python 3 + NumPy + SciPy, Node.js, Clang AVR backend, and llvm-objcopy:

```sh
python3 make_tinylpc.py
python3 build_firmware.py
node verify.js
python3 create_page.py
```

## Hardware

Connect PB1/OC0B to an RC low-pass network and the **high impedance input of an audio amplifier**, not directly to a speaker. Example: two cascaded `2.2kΩ + 10nF` RC stages and a series DC-blocking capacitor into the amplifier. Low-pass behavior and exact pitch on hardware depend on the RC oscillator and analog circuit.

Read fuses before modifying them. With an ordinary ATtiny13A and typical clock setup, `CKSEL=10` selects the internal 9.6 MHz oscillator; disabling CKDIV8 (`LFUSE=0x7A` for the cited conventional fuse mapping) avoids /8 at reset. Check your precise chip/data sheet and keep ISP/reset enabled. The code also sets `CLKPR=/1` in software.

## What limits fidelity

This is deliberately a very small LPC vocoder. Quantized 8-bit state, 4-bit coefficients, no inter-frame parameter interpolation, and a simplified excitation model make it sound robotized despite higher intelligibility. Short source phrases at 7.5kHz can never preserve the complete brightness/voice signature of an original studio recording. For materially closer **waveform** fidelity, the practical options are more memory (ATtiny85, ATmega, RP2040, or external SPI Flash) and a higher-bitrate residual / ADPCM / CELP stream. Those should be separate MicroMusic experiments, rather than pretending a true LPC2 decoder fits the 1KB ROM.
