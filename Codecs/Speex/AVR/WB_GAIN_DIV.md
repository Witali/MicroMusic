# Exact bounded HB1 gain division

Baseline: `3a0462fb`. Target: ATmega328P / AVR5, GNU ABI, AVR GCC 7.3.0,
16 MHz, explicit `SPEEX_NB3_ENABLE_ASM=1`. Only HB1's second gain division
changes; all five supported compact WB profiles share it. The separate
LPC-response division retains its original signed16 rounding cast.

The table energy is nonnegative and at most 904448. The validated divisor is
1..32767, so the rounded numerator is at most 920831, below 2^20. Divide its
high word first, then process the sixteen low bits. Before each low-bit step
the remainder is less than the divisor; doubling it and adding a bit is at
most 65533. Thus a 16-bit remainder is exact. The high-word quotient is at
most thirteen. No reciprocal approximation or rounding change is involved.

`src/wb_gain_div.S` uses 62 bytes, call-clobbered registers and no local stack,
memory accesses or interrupt masking. It preserves r1 and every callee-saved
register. `src/wb_gain_div.h` retains the original C expression, explicitly
callable even in ASM builds. Architecture identification and the separate ASM
enable select the existing backend; C is the default, including on AVR.

The isolated real-ABI test checks **1,049,060** cases: every one of the 32
table energies against all 32767 positive divisors, plus 516 boundary cases.
AVR C and ASM agree with independent BigInt arithmetic. Arbitrary callee-saved
patterns, r1, readonly inputs and stack boundaries pass on every ASM return.
The routine takes 194..322 cycles including RET, excluding the caller and IRQ.
This scalar C test does not execute or time the C decoder.

The first matched screen uses coverage, English `en_letter_a`, and Russian
`ru_slutskaya_a`, 128 frames each, with exact compact-oracle PCM and reset.

| WB3.95, all profiles linked | Before | Bounded divide |
| --- | ---: | ---: |
| Mean cycles/frame | 243283.622 | 241635.992 |
| Flash bytes | 24726 | 24734 |
| Static SRAM bytes | 1284 | 1284 |
| Peak stack bytes | 199 | 199 |

The screen saves 1647.63 cycles/frame (0.677%) for eight Flash bytes. It is
not an active-IRQ admission. Complete five-profile raw/IRQ, mixed-API and
long SPI checks are a separate validation stage. No physical board is measured.

```sh
python Codecs/Speex/AVR/tests/build_gain_div.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_gain_div.mjs Codecs/Speex/AVR/build/gain-div-unit
```

Original project optimization; the existing Xiph algorithm/table provenance
and licenses remain in their source files.
