# ATtiny13A — four-voice synthesizer, centered PWM and compact instrument algorithms

## Tested build

- MCU: ATtiny13A, 1024 bytes Flash / 64 bytes SRAM, 9.6 MHz internal RC, fuse low `0x7A` (CKDIV8 disabled).
- Output: PB1/OC0B, 8-bit Fast PWM at **37,500 Hz**. `OCR0B=128` is digital silence; the final bias is added **once**, after mixing signed contributions.
- Four voices: bowed-string lead (violin), piano, plucked guitar/bass, percussion (kick, snare, closed hat), with instrument inclusion determined at build time.
- **1009 / 1024 bytes Flash**: 688 bytes of code (including interrupts) and 321 bytes of music tables/events; **15 bytes free**.
- AVR instruction emulation of 14 seconds of the actual final HEX: **0 Timer0 overrun flags**, maximum ISR **<=256 cycles**. The separate polyphony stress suite systematically varies pitches, envelopes, and percussion and also tests the same limit.
- No physical ATtiny13A board test has been performed; real oscillator accuracy, power, RC filtering and amplifier compatibility must be checked on hardware.

## Compression improvements in this revision

| Method | Reason |
|---|---|
| `fold_bipolar` shared AVR subroutine | Violin, 1f/2f/3f/4f piano, guitar partials, and kick now share the same centered triangle/fold/shift kernel. No separate code per harmonic. |
| Two-bit shift arithmetic | All amplitudes are small signed values. `ASR` handles both polarities; no multiplying of samples or per-instrument DC offset tables. |
| `SWAP` + mask for the saw | Obtains a 4-bit centered saw with fewer instructions than subtracting 128 and shifting four times. |
| Shared release clock gate | Piano/guitar decay are updated by one common 8-tick clock test. Different register-dependent damping rates remain. |
| Preprocessor-selected synthesis | `generate.py` emits only needed instrument algorithms and chord/note tables with assembler `.if` switches. |
| Chord-root deduplication | Equivalent F# and F#m roots share one 4-byte chord table record; `R` (rest) has no unused 16-bit phase-step row. |
| Transient masking | During a drum hit, piano's weak 3rd/4th partials are omitted, reducing worst-case ISR length without muting piano fundamental/2nd partial. |
| Repeated musical sections | A one-byte playlist indexes six original musical sections rather than storing their repeated occurrences again. |

Relative to the 1023-byte acoustic version, the program shrank by **14 bytes**, despite adding correct bipolar mixing, a piano attack rasp and longer release. The code area dropped from 696 to 688 bytes; the score/tables shrank from 327 to 321.

## Sound and envelope design

- **Violin**: signed saw + folded triangle fundamental; a little 2f above low register; two-stage gradual bow attack.
- **Piano**: signed folded fundamental plus transient 2nd/3rd/4th harmonics (upper partials decay early), low register rings longer. The first attack envelope stage adds a quiet saw-like rasp from fine phase bits. During a drum hit the 3rd/4th piano harmonic is skipped to protect CPU headroom.
- **Guitar**: soft folded fundamental + second partial and short saw-like pick transient. Release proceeds over four quantized stages; stage 4 is completely silent.
- **Percussion**: decaying low triangle for kick, 8-bit LFSR snare/hat noise with different gates. Shared drum voice.
- **PWM**: each voice generates signed ~zero-centered samples, then the mixer adds fixed `+128`. A software test confirms all-voice silence produces **exactly OCR0B=128**, and the 3-second composition moving averages are within a couple of counts of the midpoint.

All of these remain tiny stylized acoustic approximations, not samples from a real violin/piano/guitar. The reference measurements in the sample project use TimGM6mb SoundFont, not a controlled recording of the instruments. There is no claim of studio-quality audio.

## Files

- `synth.S` — annotated GNU AVR assembler, one code path for four independent oscillator voices.
- `score.inc`, `config.inc` — automatically generated note/chord timing, pattern playlist and instrument flags.
- `generate.py` — converts `score.json` into minimal AVR assembly tables and removes duplicate chord roots.
- `midi_to_score.py` — extracts a compact piano-roll arrangement from MIDI for offline conversion.
- `build.py` — builds `synth.hex`, `synth.bin`, and self-contained `player.html`.
- `avr_core.js` — browser/Node instruction interpreter for the AVR instructions used by this firmware, with timed Timer0 interrupts and RCALL/RET/ASR/SWAP behavior.
- `verify.py` — opcode and sequencer timing checks, stress traversal of every playlist section.
- `stress_audio.js` — audio-path stress combinations: 3 lead pitches × 3 piano × 3 guitar × 5 percussion states; asserts no missed PWM periods and duty bounds.
- `render_wav.js` / `preview.wav` — audio rendered by executing the real HEX.
- `register_demo.js` / `register_demo.wav` — isolated piano, guitar, violin notes to compare timbres.
- `player.html` — offline audio player plus PWM waveform and running average duty vs 128.
- `comparison_metrics.csv`, `acoustic_spectrum_comparison.png` — optional numerical comparison against available *sample-based* timbres; not raw live-instrument measurements.
- `fuses.txt` — startup clock settings and avrdude commands.

## Build

```bash
python3 build.py
python3 verify.py
node stress_audio.js
node render_wav.js 14
node register_demo.js
```

Building with GNU AVR toolchain is preferred:

```bash
avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles -Wl,-Ttext=0 \
  -x assembler-with-cpp -I. synth.S -o synth.elf
avr-objcopy -O ihex synth.elf synth.hex
```

`build.py` also supports the LLVM AVR IAS installed in the validation environment and applies only the two tested kinds of AVR `LDI` relocation against a single `.text` section. The HEX is genuine AVR opcodes, not a JavaScript reimplementation of timbres.

## Analog output

PB1/OC0B -> one or two RC low-pass stages (roughly 7–10 kHz corner depending on the load) -> DC-blocking capacitor -> high-impedance amplifier input. **Do not directly drive a low-impedance speaker from the ATtiny13A pin.** For lower noise use a properly buffered active low-pass or resistor-network filter. The browser plot shows duty-cycle *averages* at the audio update rate, not 9.6 MHz PWM edge detail.

## Potential next compression step

A tiny shared **4-bit waveform dictionary** (e.g., 16 4-bit samples = 8 bytes per waveform) selected by register can further trade FLASH for instrument variety. But decoding nibble tables at **37.5 kHz** would also cost valuable cycles and introduce aliasing, so it should be benchmarked against the current shared arithmetic primitive before being used. The current implementation favors cheap shifts and the shared kernel.
