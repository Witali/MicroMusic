# LPX3 pulse-pattern experiment

The 3-bit LPX3 streams themselves **do not fit** into ATtiny13A. Each clip was
processed offline to extract excitation residual pulse shapes and train four
8-sample excitation templates (signed 4-bit values). Each clip's trained table
is exactly 16 bytes and can be placed in the ATtiny13A's 64-byte EEPROM.

Two bits per 256-sample speech frame are used for a pattern selector:
`chego` = 9 bytes, `otvechaesh` = 8 bytes, `vinni` = 22 bytes.

`excitation_profiles.eep` is **not useful with the supplied HEX binaries**.
Those HEX files implement the previous TinyLPC algorithms and do not read the
new EEPROM table. This is a training and footprint experiment, not completed
LPX3 AVR firmware. Flash usage for the modified decoder has not been measured.

The JSON metric only evaluates selected eight-sample excitation pulse shapes.
It is **not** a speech-quality metric; the full synthesis filter has not been
recomputed for these pulses, and phase, F0, energy and consonants matter.

To train again:

```
python tools/train_lpx3_pulses.py --input references/chego/voice_v3_3bit.lpx3 --frames 36 --out lpx3_experiment/chego
```

Plan for integration into a future more compact AVR decoder:
1. Store 16-byte dictionary in EEPROM.
2. In the LPC frame header, reserve two otherwise unused bits for the pattern
   selector (format-dependent); avoid adding a separate selector stream when
   possible.
3. Load a signed 4-bit pattern value for each sample at the beginning of a
   glottal period, apply energy scaling, and use an LPC lattice as before.
4. Re-optimize LPC gains and coefficients with analysis by synthesis, inspect
   clicks and objective speech metrics, then independently execute the HEX.
