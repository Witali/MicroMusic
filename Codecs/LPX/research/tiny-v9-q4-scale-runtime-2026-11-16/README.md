# Reconstruct the Q4 scale during AVR25 v9 block setup

For scale index `i`, select mantissa 4194 when it is even and 5931
when it is odd. With `a=i>>1`, the original unscaled step is the
mantissa divided by `2^(16-a)` and rounded to nearest. Shift
the mantissa by `a-12`, using a right shift when the exponent is
negative. Adding eight and clearing the low nibble now gives the same
rounded Q4 value. The largest rounded result is 47456 and fits a word.
The selectable C backend keeps its table.

Two small AVR byte-shift loops and early exit from the headerless
second half of Sparse80 pay for the scale reconstruction. The paired
comparison against `0f746634` uses AVR-GCC 7.3.0 with GNU AVR ABI,
ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. All 22 simavr
1.6 IRQ workloads save 36 program bytes, to 4434–4435 B excluding the
embedded LPX. Mean decoder CPU plus IRQ time falls by 0.068–0.376
cycles per sample. The largest measured mean is 1623.39 cycles per
sample. Each workload's longest decoder call is at least seven
cycles shorter.

All 308,339 PWM samples equal the preceding build and portable C.
Zero underruns were observed. Direct AVR probes cover all 32 scales
with ASM, C and forced-generic backends, and 4608 shifts covering every
byte, direction and width from zero to eight. Fourteen further IRQ
cases cover replay, short tails and damaged streams. All 18 existing
WebUI images rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-q4-scale-runtime --target tiny --baseline 0f746634
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-q4-scale-runtime-web --run
```
