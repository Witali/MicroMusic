# MicroMusic MiniLPC Packed — Lossless-by-construction frame repacking

This is a speech-parameter bitstream optimization (not raw waveform compression and not LPX3). It retains the eight-stage LPC filter and exact bitwise PCM output.

| clip | Old Flash | New Flash | Flash saved | Old speech | New speech |
|---|---:|---:|---:|---:|---:|
| chego | 601 | 577 | 24 | 216 | 180 |
| otvechaesh | 571 | 552 | 19 | 186 | 155 |
| vinni | 907 | 840 | 67 | 522 | 435 |

- `chego` and `otvechaesh`: 4-bit pitch code (0 for unvoiced, 1..15 for periods 16..30), plus 4-bit gain in the same first byte.
- `vinni`: K8=0 in every frame; gain shares a byte with K7, and K8 is reconstructed at decode time.
- All three byte-for-byte PCM comparisons matched (9216, 7936, 22272 audio samples).
- 0 missed Timer0 interrupts in independently running AVR emulator.
- `index.html` is an offline browser comparator. On Play it uses verified PCM for fast listening; Verify HEX runs the actual instructions and compares samples.
- Each folder stores baseline and repacked assembler, HEX, BIN, speech bytes and PCM from the actual AVR emulator.
- Actual hardware remains untested. ATtiny13A flash limit is 1024 bytes, oscillator 9.6MHz, PWM via PB1/OC0B.
- Copyright note: sample data is derived from user-supplied cartoon recordings, retain for private evaluation unless properly licensed.
