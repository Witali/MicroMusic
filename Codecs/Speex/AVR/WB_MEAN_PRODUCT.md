# One exact product for the NB1 vocoder mean

Baseline: `4107d9f3`, with exact bounded HB1 division. Target: classic AVR5 /
ATmega328P, 16 MHz, GNU ABI, AVR GCC 7.3.0, explicit ASM. NB2.15 and its
compact WB3.95 combination use this mean; the other submodes do not.

The original update is `floor((26214*old + 6554*value + 16384)/32768)`.
Because the coefficients sum to 32768, it equals
`old + floor((6554*(value-old) + 16384)/32768)`. Both inputs are signed16,
but their difference needs seventeen signed bits. If signed16 subtraction
wraps, the missing +/-65536 contributes an exact integer correction of
`+/-13108`, since `6554*65536/32768 = 13108`. AVR's V flag detects this case;
the wrapped result's sign chooses the correction. LDI preserves these flags.

The single signed16 product needs four hardware MUL instructions instead of
eight in the old two-product inline expansion. Rounded extraction keeps bits
15..30; additions of the base/correction are modulo 16 bits, as is the
original returned word. The original convex weighted sum plus rounding fits
signed32, so the algebra introduces no signed overflow or approximation.

`src/lowrate_mean.S` is an 82-byte shared subroutine. It uses only GNU
call-clobbered r18..27 and flags, clears r1, and adds no local stack, hardware
memory access or interrupt masking. The original two-product C expression
remains explicitly callable in `lowrate_mean.h`, including in ASM builds.
Default/unsupported architectures use C through the existing architecture
selector plus separate ASM enable. Memory access is independent of selection.

The isolated real-ABI test checks 1,212,335 pairs: nine complete signed16
sweeps per operand (without duplicate edge intersections) and 32768 random
pairs. Both overflow directions, C fallback and ASM match independent BigInt
arithmetic. Arbitrary callee-saved patterns and r1 pass every return. Every
call executes exactly four MULs and takes 43..48 cycles including RET,
excluding CALL and IRQ. This test does not execute or time the C decoder.

## Matched initial screen

AVR GCC 7.3.0, existing Os/O2/O3/LTO/mcall-prologues/mrelax, avr8js 0.21.1.
Same three 128-frame streams: coverage, English `en_letter_a`, Russian
`ru_slutskaya_a`; exact established-oracle s16 PCM. All optional modes linked.

| Screen | Before | One product |
| --- | ---: | ---: |
| WB3.95 mean cycles/frame | 241635.992 | 238690.076 |
| WB3.95 Flash / static SRAM / peak stack | 24734 / 1284 / 199 B | 24690 / 1284 / 199 B |
| NB2.15 Flash / static SRAM / peak stack | 17302 / 1104 / 118 B | 17216 / 1104 / 112 B |

WB saves 2945.92 cycles/frame (1.219%) and 44 B Flash. NB saves about 3771
cycles/frame and 86 B Flash, with six fewer peak stack bytes. A subroutine
therefore improves both measured speed and size here. Exactly 160 mean calls
per NB1 frame remove **640 hardware multiplies/frame**; this is not the
multiply count for the complete decoder. Complete corpus/IRQ/SPI admission is
a separate stage. No physical board or analog output measurement is claimed.

```sh
python Codecs/Speex/AVR/tests/build_low_mean.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_low_mean.mjs Codecs/Speex/AVR/build/mean-unit
```

Original project algebra/register implementation, retaining Xiph algorithm
provenance and licenses in the surrounding source/vendor files.
