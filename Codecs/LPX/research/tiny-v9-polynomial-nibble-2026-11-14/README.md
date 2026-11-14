# Compute the small LPC polynomial product in four rounds on AVR25

V9 uses two separate floors when a polynomial coefficient exceeds the direct
product bound. The second product multiplies a truncating-division remainder
in −15..15 by a cosine factor in −8192..8192. Four unsigned carry rounds
compute the product divided by 16. At that scale the signed corrections for
the coefficient and the remainder are integral. Extracting the corrected
high byte gives the same floor after division by 4096. The direct product,
split threshold, upper product and separate rounding points are preserved.
The helper has a selectable C multiplication and shift.

ATtiny88 / AVR25, AVR-GCC 7.3.0, GNU AVR ABI, `-Os -flto -mcall-prologues
-mrelax`, two LPC segments, MUL16 unroll 2, FIFO32/prefill24. Compared with
`8fd7145b`, the program falls from 5146–5147 B to 5066–5067 B excluding
unchanged audio. In simavr 1.6 at 16 MHz and 8 kHz, all 308,339 PWM samples
match the baseline and independent C reference on 22 interrupt-active
workloads. All play to completion with zero underruns. Mean decoder CPU
time plus IRQ falls by up to 0.46 cycles/sample on seven workloads and ties
on 15. Peak decoder CPU time falls by up to 152 cycles and never grows.
Peak stack stays at 54 B and per-load minimum queue occupancy is identical.

The arithmetic probe adds 3406 signed remainder/cosine pairs to the
179,682-case suite. C, opt-in ASM and forced generic pass with active IRQ.
All 18 WebUI images rebuild byte for byte.
[Per-load measurements and probe counts](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/poly-nibble-matched --target tiny --baseline 8fd7145b
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py \
  build/poly-nibble-math --mul16-unroll 2 --saturated-products
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/poly-nibble-math
```
