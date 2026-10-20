# ATtiny13A: 4-voice acoustic-inspired player, 1023-byte version

## What is included

- `synth.S`: GNU AVR assembly firmware with algorithm-level comments.
- `synth.hex`: **1023 bytes** in Flash (Intel HEX). `synth.bin` is same payload.
- `config.inc`, `score.inc`: generated options/music tables.
- `generate.py`: automatic packing and instrument selection (only the desired instruments are compiled).
- `midi_to_score.py`: preprocessing MIDI to an arrangement compatible with the compact player.
- `build.py`: source + score regeneration, GNU toolchain where available or LLVM AVR assembler fallback, HEX and HTML packaging.
- `player.html`: offline audio player using an AVR instruction interpreter, no simulated JS musical oscillators.
- `avr_core.js`: emulator used by the player; `verify.py` checks instruction timing/score execution.
- `preview.wav`: 14 s of the actual firmware output interpreted from HEX.
- `register_demo.wav`: isolated piano, nylon guitar and violin tones from AVR firmware.
- `register_demo_baseline.wav`: same demo rendered using the preceding **917-byte** firmware.
- `acoustic_spectrum_comparison.png` and `comparison_metrics.csv`: visual/CSV spectra from sampled-instrument reference vs the two AVR versions.
- `soundfont_reference.py`, `reference_compare.py`, `compare_all.py`: repeatable offline benchmarking against available TimGM6mb SoundFont (not raw anechoic recordings).

## Acoustic comparison: limitations and method

The reference used for the numerical comparison is an on-device, **sample-based GM SoundFont, TimGM6mb.sf2**: patch 0 Acoustic Grand Piano, 24 Nylon Guitar, 40 Violin. It is a *sampled instrument proxy*, NOT a direct comparison with raw acoustic recordings by a named performer. It should not be interpreted as a ground-truth acoustic signature of every real instrument. The external University of Iowa sample archive at https://theremin.music.uiowa.edu/MIS.html is a more suitable set of raw recordings for future comparisons. Its raw audio was not downloaded or numerically analyzed in this deliverable.

The analysis compares early note 40–160 ms for all instruments at source pitches and measures harmonic amplitudes H1–H8 relative to H1; align peaks within a small band, clamp below −50 dB for a weighted mean absolute deviation. This is **not** a psychoacoustic similarity score and cannot model attack noise, vibrato, inharmonicity or instrument-specific resonances fully.

| Instrument | Old spectral error | New spectral error |
|---|---:|---:|
| Violin (G3, D4, A4, D5) | 4.6 dB | 4.0 dB |
| Piano (C3, D4, A5) | 16.3 dB | 7.3 dB |
| Guitar (G2, D4, A4) | 9.5 dB | 6.0 dB |

### What changed

- **Violin:** keeps the original saw + triangle low register. From D4 upwards a weak second harmonic from doubled folded phase is added. The low-string baseline is identical. The model still lacks realistic bow noise, formants and dynamic changes.
- **Piano:** doubles, triples and quadruples the existing accumulator high byte to generate the 2nd/3rd/4th harmonics. More harmonics survive in bass, fade quickly in the middle, and are suppressed on high notes. No multiplication or samples. Real piano strings are mildly inharmonic; this code remains harmonic.
- **Nylon guitar:** adds phase-doubled second harmonic for first two release stages, louder on bass notes, plus a weak attack saw to restore the broadband transient. The envelope remains a coarse stepped approximation, not a physical plucked-string simulation.
- **Drums:** unchanged, one combined kick/snare/hat rhythm voice.

## Hardware configuration / fuse

- ATtiny13A, **internal 9.6 MHz RC**.
- Low fuse `0x7A` selects 9.6 MHz with CKDIV8 unprogrammed (disabled). Confirm your exact device and fuse state first.
- PWM Timer0 Fast PWM TOP=255, divide-by-one -> **37,500 Hz** hardware PWM on PB1/OC0B.
- Maximum documented/runtested interrupt period **256 CPU cycles**. Longest stressed firmware ISR path **172 cycles** plus hardware interrupt latency handled by verifier. Four oscillators and envelope/rhythm update use the same ISR.
- On-board output is PWM, **not DAC**: an external low-pass filter, coupling capacitor and amplifier are still required. Two RC low-pass stages around 7–10 kHz and high-impedance audio-amplifier input are a starting point.
- 1023/1024 Flash bytes means modifying the score or turning on other timbre variants may trigger a build-size error; check before flashing.

AVRDUDE **after confirming the hardware programmer and device** (write the fuse only if you intend to change the oscillator setup):

```bash
avrdude -c usbasp -p t13 -U lfuse:w:0x7A:m
avrdude -c usbasp -p t13 -U flash:w:synth.hex:i
```

## Build and evaluate

```bash
python3 build.py
python3 verify.py
node render_wav.js 14
node register_demo.js
python3 soundfont_reference.py            # needs libfluidsynth and TimGM6mb.sf2
python3 compare_all.py
```

For the reference script, set `SOUNDFONT_PATH=/path/to/TimGM6mb.sf2` if it is not installed at `/usr/share/sounds/sf2/TimGM6mb.sf2`. Python comparison requires NumPy, SciPy, Matplotlib. `build.py` supports GNU AVR GCC (`avr-gcc`, `avr-objcopy`) or, as done here, Clang AVR assembler with a narrowly scoped relocation resolver. The fallback is not a general AVR linker.

The reported cycle tests execute the actual assembled machine instructions; they are not a hardware measurement. Browser audio is the emulated PWM duty stream, not a physical analog PWM waveform. Please validate sound, frequency, fuses and output filter on the actual MCU.

## License note

TimGM6mb.sf2 and the reference WAVs were **not included in the ZIP**; obtain a legally usable SoundFont separately and recreate the analysis locally. The package only contains firmware-created audio, figures, numerical measurements and analysis scripts.
