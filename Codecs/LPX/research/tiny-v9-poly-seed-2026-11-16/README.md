# Seed the AVR25 v9 LPC workspace with signed 24-bit stores

The first coefficients fit signed16. Initialize the unit and first two
coefficients in the same signed24 representation used by the rest of
the recurrence. The four-byte slot stride retains the ring's wrap
alignment. The fourth byte is padding in this build. The selectable C
decoder uses its existing polynomial representation.

The paired comparison uses `b0ac2064`, AVR-GCC 7.3.0 with GNU AVR ABI,
ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. In simavr 1.6
all 22 full IRQ workloads save 14 program bytes, down to 4560–4561 B
excluding the embedded LPX. Mean decoder CPU plus IRQ falls by up to
0.106 cycles per sample. The largest measured mean is 1626.96 cycles.

The 308,339 PWM samples match the previous build and portable C.
Zero underruns were observed with at least 24 queued samples during
production, a peak of 51 stack bytes and 433 B of static SRAM.
Fourteen further IRQ controls cover short tails, repeated playback
and truncation. Eighteen WebUI images rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-poly-seed --target tiny --baseline b0ac2064
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-poly-seed-web --run
```
