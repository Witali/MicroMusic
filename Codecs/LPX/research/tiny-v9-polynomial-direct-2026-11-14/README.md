# Bound the upper correction of a direct polynomial product on AVR25

Split the polynomial operand into a signed low word and an upper correction
in −4..4. Multiply the low word with the existing signed16 routine. Most
calls have a zero upper correction and can shift the product immediately.
For the other calls a byte counter visits the remaining bits of its absolute
value. A negative multiplier negates the coefficient modulo 65536. The low
16 bits of this product correct the upper word of the 32-bit product before
the Q12 floor. This preserves the direct bound of ±250000 and the independent
split product for wider inputs. The selectable C implementation computes
the same bounded product and floor.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, two LPC segments, MUL16 unroll 2 and FIFO32/prefill24.
Compared with `cbb3fec4`, program Flash shrinks by 12 B to 5034–5035 B
excluding the unchanged audio. Across 22 simavr 1.6 loads at 16 MHz and
8 kHz, all 308,339 PWM samples match the baseline and C reference. There are
zero underruns. Mean active decoder cost plus the complete IRQ improves by
up to 4.73 cycles/sample on 21 loads, with one tie. The largest workload
mean falls from 1655.13 to 1653.58. Peak decode CPU cost falls by 215–759
cycles per load, and peak observed stack drops from 54 to 53 B.

The active-IRQ arithmetic probe adds 4275 cases covering signed low-word
transitions and the legal extreme factors. C, explicit ASM and forced generic
pass all 183,957 tests. All 18 WebUI images rebuild byte for byte.
[Per-load measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/poly-direct-matched --target tiny --baseline cbb3fec4
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py \
  build/poly-direct-math --mul16-unroll 2 --saturated-products
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/poly-direct-math
```
