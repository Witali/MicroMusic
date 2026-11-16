# Convert the clipped Q14 sample directly to PWM on AVR25

The postfilter already clips samples to the signed range −16384…16384.
For `x = sample + 16384`, gain 130 and the standard midpoint give
`floor((x + floor(x/64) - 192)/128)`. The discarded part of `x/64`
cannot cross the next integer boundary. The numerator lies in
−192…33088. A left shift extracts the PWM byte and sets carry when
the unsigned result is out of range. In that case bit 14 distinguishes
the two rails. The portable C path retains the general PWM conversion.

On ATtiny88 with AVR-GCC 7.3.0 and the GNU AVR ABI at 16 MHz and 8 kHz,
the universal v9 recipe uses SRAM512, LPC2, MUL16 unroll2,
FIFO32/prefill24 and `-Os -flto -mcall-prologues -mrelax`. The image
is 32 B smaller on all 22 loads, for 4740–4741 B excluding compressed
audio. Compared with `31d8aa57`, average decoder CPU time plus IRQ improves
by 10–15 cycles/sample. Worst observed mean is 1633.53 cycles/sample.
At least 24 samples remain queued before output. Peak stack remains 51 B.
All 308,339 PWM samples match the baseline and C reference with active
IRQ in simavr 1.6 and zero underruns.

The direct arithmetic probe covers every one of the 32,769 legal input
values on C, AVR25 ASM and the forced generic backend with active IRQ.
All 18 previously retained WebUI images rebuild byte for byte.
[Measurements](measurements.json).

An independent six-round shared multiply loop saved 62 more bytes in a
prototype. In four IRQ controls it took up to 16 extra cycles/sample.

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/pwm-bounded-matched --target tiny --baseline 31d8aa57
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py \
  build/pwm-bounded-math --mul16-unroll 2 --saturated-products
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/pwm-bounded-math
```
