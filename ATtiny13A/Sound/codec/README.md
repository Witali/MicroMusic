# MicroMusic · MiniLPC8-VBR (ATtiny13A)

Experimental **new-only** variable-length frame format for a tiny 8-stage LPC speech synthesizer. The AVR firmware **does not** implement legacy fixed-frame decoding. The fixed-frame samples are used *only* by the computer-side rate–distortion trainer and for A/B comparisons.

## Firmware format

Audio: internal 9.6 MHz RC oscillator (CKDIV8 cleared by code), Timer0 Fast PWM 37.5 kHz on PB1/OC0B, PCM updates 7,500/s, frame duration 256 output samples (34.13 ms).

Every frame begins with two bytes:

- Byte 0: unsigned pitch period; zero is unvoiced; `0xFF` terminates the stream and loops to its first frame.
- Byte 1: gain bits 0–3, excitation profile bits 4–5, **VBR type bits 6–7**.

| Type bits | Total bytes | Action |
|---|---:|---|
| `00` | 6 | Set all eight LPC reflection coefficients |
| `01` | 2 | Keep all eight previous coefficients |
| `10` | 4 | Update K1…K4 only |
| `11` | 4 | Update K5…K8 only |

Coefficients are packed 4-bit integers, `signed_k = nibble - 8`. The first frame must be full. **Only this new bitstream format is supported on the MCU.** No old-format decoder, previous frame table or format autodetection is linked into the firmware.

The encoder chooses between these alternatives automatically. It synthesizes the candidate output with the *exact* 8-bit arithmetic of the firmware, calculates STOI on the original audio, penalizes large PCM jumps, and balances savings against changes in quality. The rate-distortion optimization is lossy, even though the same decoder mathematics and sample rate are retained.

## Memory and measured results

| Voice / phrase | Fixed Flash | VBR Flash | Fixed speech | VBR speech | STOI fixed → VBR |
|---|---:|---:|---:|---:|---:|
| Chego / «Чего тебе нужно?» | 581 B | **533 B** | 216 B | **144 B** | 0.667 → **0.671** |
| Otvechaesh / «Что ж ты не отвечаешь?» | 551 B | **505 B** | 186 B | **116 B** | 0.622 → **0.628** |
| Vinni / «Сова! Открывай! Медведь пришёл!» | 887 B | **713 B** | 522 B | **324 B** | 0.744 → **0.747** |

Flash code size for the new format is **388 bytes**, compared with 364 bytes in the prior fixed-format firmware; the extra 24 bytes implement VBR parsing. The new firmware still fits comfortably into 1,024 bytes and does not use EEPROM.

The compiled HEX programs were executed by the included AVR interpreter. **39,424 audio samples were compared with the mathematical model: 0 differences**. No Timer0 overflows or 7.5 kHz output deadlines were missed in this emulation (maximum ISR duration: 28 cycles). This is **not** a physical-hardware validation.

## Rebuilding

Requirements: Python 3, LLVM/Clang with AVR target, `llvm-objcopy`, Node.js. For training additionally install the packages from `requirements.txt`.

```bash
python3 build.py    # Build all three firmware.hex files
node verify.js      # Execute every machine instruction and compare PCM samples
python3 make_player.py # Regenerate the offline index.html
```

After changing your audio or fixed training input, retrain with:

```bash
python3 optimize_vbr.py --passes 1
python3 build.py
node verify.js
python3 make_player.py
```

Training with `--passes 2` and several lambda values searches more candidates but can take several minutes. It is safe to change the rate-distortion prices using `--lambdas`. The quality guard is STOI at most 0.007 worse than the original compressed decoder, plus no extra jumps ≥48 PCM steps. All selected bundled examples actually scored slightly **higher** than their fixed-frame baselines, but STOI is not a subjective timbre metric.

To replay a single prepared firmware, write its `.hex` to the ATtiny13A with a compatible programmer, leave reset and ISP enabled, use a low-pass filter after PB1/OC0B, and do not connect a loudspeaker directly to the pin. Keep the 9.6 MHz clock and suitable VCC. Physical hardware is untested.

## Layout

- `samples/chego`, `samples/otvechaesh`, `samples/vinni`: AVR `.S`, compiled `.hex` and `.bin`, `.vbr` bitstreams, speech frames for training, reference PCM, mode selections, metrics.
- `references/`: original user-provided and LPX3 comparison WAVs.
- `vbr_codec.py`: framing/pack/unpack implementation.
- `reference_model.py`: fixed-point reference LPC8 synthesizer matching AVR arithmetic.
- `optimize_vbr.py`: computer-side analysis-by-synthesis training with STOI feedback.
- `avr_emulator.js`, `verify.js`: independently run the real AVR machine instructions.
- `make_player.py`, `index.html`: autonomous HTML with selects, Web Audio playback, waveform, downloads and machine-code verification.

## Publication and copyright

The **full private** bundle contains audio taken from copyrighted cartoons and derived coded speech. Do not publish these audio recordings, encoded streams, firmware embedding that speech, or an HTML page embedding the audio, without permission. A separate source-only archive includes a **synthetic** input generator and a runnable demonstration without copyrighted audio.
