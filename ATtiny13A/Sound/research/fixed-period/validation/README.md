# Full decoder integration fixture

`model.json` is a synthetic arithmetic/control fixture, not a speech-quality
demonstration. It uses two nonzero 32-point waveforms, six frames, changing
pitch/gain/white-residual levels, a nonzero initial phase, and shift-7 DC
correction. The remaining fourteen waveform slots are unused trailing words
and are excluded from the specialized AVR tables without changing synthesis.

The actual speech firmware template builds to 876 bytes: 826 code plus 50
data (32 waveform, 18 parameter stream). The real ATtiny13 linker and all
emulator engines retain their 1024-byte Flash limit. No enlarged-emulator
exception is used.

The retained `build.json` records exact agreement for 1152 PWM samples across
three repetitions in the reference JS, optimized WASM, and unoptimized WASM
engines. Sample intervals are 1279–1281 CPU cycles at 9.6 MHz, with no lost
overflows or samples. Minimum SP is 0x93, above the data boundary 0x6a.
The first and second repetitions differ at 48 sample positions because the
DC estimator is carried across phrase seams. Phase/noise/history restart at
each phrase, matching the independent integer model.

This exercises the complete specialized white-residual playback path,
including the frame reader, both interpolation clocks, gain rounding, noise,
PWM scheduling, stack, and DC continuity. It does not validate FIR/unvoiced
paths absent from this model, prove that the retained speech clips fit in
Flash, or substitute for a physical hardware test. Real speech budgets are
reported separately and remain oversized.

Reproduce with the toolchain/dependency paths configured for your machine:

```text
python tools/build-fixed-period.py --model ATtiny13A/Sound/research/fixed-period/validation/model.json --output build/fixed-period/validation --avr-bin <avr-toolchain-bin> --node <node-executable>
```

Generated assembly, configuration, object, ELF, binary, disassembly, and PCM
remain under ignored `build/`. Only this model and its measured report are
retained here.
