# Wider Q3 lattice experiment

The original HQ4 lattice multiplies each signed four-bit coefficient by 1/16,
so its reflection coefficients cover only -0.5 to +0.4375. This profile uses
1/8 and the encoder restricts values to -7 through +7, giving -0.875 to +0.875.
The stronger resonances require a separately fitted stream. Playing an existing
HQ4 stream unchanged is incorrect and can cause internal arithmetic overflow.

`hq4.S` is 408 bytes. `hq4-t1.S` adds an independent first-order output stage,
`previous = s8(x + previous - (previous >> 1))`, for a 420-byte core. Each Q3
multiply uses three arithmetic high-byte shifts and low-byte rotates. The
sample rate, pulse shape, coefficient packing, frame timing, and one-shot EOF
convention match the original profile. EEPROM is unused.

`hq4_q3.py` is the exact numerical oracle. It counts subtraction, filter-state,
signed-negation, and output-stage wrap events. `tools/probe-hq4-q3.py` rejects
any candidate with such a wrap, PWM peaks above 115, or adjacent steps >=48.
Seeds include half-scale retained Q4 coefficients and newly analyzed order-eight
LPC. Local proposals fit the actual byte decoder, not a floating-point surrogate.

The optional `--spectrogram` objective is STOI minus 0.35 times the shared
reference-derived spectrogram loss. It compares fine ridges, broad mel envelopes,
unsupported energy, and missing energy. It is a diagnostic engineering target;
its numerical improvement does not establish a natural-sounding voice.

Run `tools/test-hq4-q3.py` for exhaustive signed multiplication and independent
Q4-oracle equivalence on the shared coefficient subset. `--build` assembles the
new AVR source and checks the complete PCM plus twice as much midpoint silence
with all three repository emulator engines. A fit claim requires that report.

Public Vinni results, retained starting/final models, and reproduction commands
are in `../../research/hq4-q3/`. Existing release streams remain unchanged.
