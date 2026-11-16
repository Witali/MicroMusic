# Decode each AVR25 v9 LSF vector with one Rice setup

The Rice escape width depends on the profile and delta mode, which are
fixed across each ten-index vector. Compute it before the loop. The
one-based monotonic cursor starts at zero and each successful iteration
assigns a value from 1 to 64, so byte comparisons suffice. Set the
initialization flag once when the first spectrum is accepted. The
portable C reader remains selectable and the same LPX streams serve
both readers.

The paired comparison against `85972e20` uses AVR-GCC 7.3.0 with GNU AVR
ABI, ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. In simavr 1.6
all 22 full IRQ workloads save 24 program bytes to occupy 4482–4483 B
excluding the embedded LPX. Mean decoder CPU plus IRQ falls by
0.037–0.222 cycles per sample. The largest measured mean is 1623.82.
All 308,339 PWM samples match the previous build and portable C. The
minimum producer queue is 24 samples, with zero underruns and a 51 B
peak stack. All 18 existing WebUI images rebuild byte for byte.

Ten further IRQ cases compare bad LSF vectors for both P4 and P6,
including attempts to cross zero, repeat a neighbor or exceed the
profile bound. Each build drains the same 320-sample prefix and
reports the same corruption error.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-lsf-invariants --target tiny --baseline 85972e20
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-lsf-invariants-web --run
```
