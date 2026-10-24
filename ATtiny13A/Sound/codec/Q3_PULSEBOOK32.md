# Packed32-tap Q3 source

`q3_pulsebook32.py` is a separate exact-byte PC oracle. Four rows of32 signed
coefficients in−7..7 occupy exactly64 EEPROM bytes: coefficient+8 is a nibble,
even lag is low, odd lag is high, rows are consecutive. Nibble0 is reserved.
`pack_book` and `unpack_book` validate before narrowing. The model schema is
`hq4-q3-pulsebook32-v1`; there are no per-frame flags or extra stream bytes.

`render(frames, durations, pulsebook, tilt_shift=1, nearest=False)` returns
unsigned8-bit PWM and four arithmetic counters, like the16-tap oracle. Frame
packing, sample timing, final-frame reset, period0 LFSR, Q3 signed arithmetic
and output tilt are unchanged. `legacy_tables()` pads the16-tap tables with
zeros. Arbitrary old tables padded this way produce identical bytes and
counters, including the floor and nearest variants.

Run `tools/test-q3-pulsebook32.py` with the repository codec dependencies.
PC scores do not establish AVR timing, total Flash size or a quality gain.
Use the separate real firmware builder to qualify retained candidates.
