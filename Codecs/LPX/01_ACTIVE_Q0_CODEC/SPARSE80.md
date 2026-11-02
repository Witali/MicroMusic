# Optional LPX sparse80 decoder

The explicit `LPX4_ENABLE_SPARSE80=1` option adds version8/mode15 to the
compact decoder. It is intended for low-rate speech, including a complete
2 kbit/s file budget; the mode number does not fix the bitrate. Ordinary
v5/P4 remains useful near3 kbit/s. A1.5 kbit/s preset is not part of this
release.

This option requires `LPX4_COMPACT_ONLY=1`, `LPX4_ENABLE_SPEECH=1` and
`LPX4_ENABLE_SPEECH_COMPACT=1`. Use the same definitions in the core and
all callers. It defaults to0: old v5 builds retain their original output,
strict flag validation, layout and compiled image. Version8 is rejected
without the explicit option. Arithmetic C/ASM selection remains independent.

## Syntax and reconstruction

The syntax is unchanged from the separate
[original research format](../research/lpx-s15-2026-11-01/README.md).
Each320-sample packet stores an ordered6-bit LSF vector using the existing
bounded Rice gap/delta/repeat codes, one15-bit scale/lag/gain group and four
7-bit80-sample innovations. Fixed packet fields cost1075 bit/s before
spectra, the22-byte header and zero padding. Stored final packets are complete
even when the output sample count ends partway through one.

The direct parser reuses the existing LPC and excitation state. It reads
parameters once per320 samples and one position/sign pair per80 samples.
It adds no state fields, tables or alternate synthesis arithmetic. Final
packet validation drains unused stored innovation fields without emitting
samples, rejects truncation/extra bytes/nonzero padding, and keeps the exact
declared output length. Ordinary v5 flags cannot enter this parser.

The [host adapter](tools/speech_sparse80.py) packs/unpacks the same syntax
and expands it into ordinary v5/P6 as an independent reference. Each sparse
innovation is followed by the required zero innovations; spectral values,
pitch, rounding, saturation, deemphasis and brightness are unchanged. This
larger reference stream is never used to calculate the sparse file's size.

## Validation and building

`tests/test_speech_sparse80.py` compares packed bytes, decoded fields and
reference expansion with the original research implementation.
`tests/test_sparse80_direct.py` compares direct native PCM/PWM against the
ordinary v5 decoder and the independent model, including all320 final-tail
positions, LPC segment counts1/2/4, random spectra/parameter/filter bounds,
malformed streams and the pointer/counter C fallbacks.

`tools/build_release_player.py --enable-sparse80` compiles the actual standalone
AVR player. Observer validation additionally requires `--expected-pwm` from
the independent expansion oracle. The default build does not enable sparse80.
Target Flash, stack and real-time admission must be measured using the whole
linked player with active interrupts for the selected stream. A native format
test or a smaller compressed file does not establish target timing.

The SRAM512 Tiny88 builder and verifier also accept `--enable-sparse80`.
It remains independent from `--enable-asm` and `--asm-isr` in the builder.
The fixed header checks raw mode15, then specializes the existing internal
P6+sparse80 arithmetic; the default C reference keeps dynamic parameters.
All 320 final sample positions are checked against ordinary-v5 expansion
with fixed header constants and the SRAM512 workspace enabled.
