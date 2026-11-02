# Exact bounded forced-pitch products

Target: ATmega328P / classic AVR5 with MUL/MULSU, GNU AVR ABI, AVR GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, O2 scalar wrappers. Original project
arithmetic/register adaptation of the pinned Xiph Speex forced-pitch formulas.
Retain existing Xiph BSD provenance. The initial scalar prototype below is now
connected to NB3.95/WB5.75. Scalar timings exclude interrupts; complete-image
and real-time admission are recorded separately below.

For signed16 x and coefficient c in 0..63:

```c
(x * (c << 7) + 4096) >> 13 == (x * c + 32) >> 6
```

The exact common factor is 128, including the rounding bias. Preserve ties
toward positive infinity for negative values. The product plus bias fits
signed22 and the rounded result fits signed16. On AVR form the signed24
product with `MULSU(high(x),c)` and `MUL(low(x),c)`, add 32, shift left twice
and retain its high word (original bits6..21). Two byte products replace the
generic full-word product. CLR of r1 preserves carry between the low-product
ADD and the high-byte ADC, and restores the GNU zero register.

The inline ASM uses early-clobber word constraint `=&w` for the result,
`=&d` for the low-byte scratch and `a` for inputs. Thus SUBI/SBCI operands
are high registers, MULSU inputs are r16..r23, and outputs cannot overlap
inputs. Clobber r0/r1/cc explicitly. Architecture matching plus the existing
separate ASM-enable switch selects it; explicit `speex_forced_q6_c` remains
available on AVR. Hardware memory access is independent.

The four-bit coefficient code also permits exact narrowing:

```c
(2185L * (code << 6) + 16384) >> 15
    == (uint16_t)(2185u * code + 256u) >> 9
```

For code 0..15 the numerator is at most 33031, so unsigned16 is necessary
and sufficient (signed16 would overflow). Return 0..64 without clamping:
submode8 clamps to63 separately; submode1 must retain code15 ->64.

Evidence: all 4194304 signed16 x / 6-bit c pairs execute through selected
AVR ASM and match both exact integer formulas. Another 9856 cases per
backend compare selected/default C, explicit C, the original expression and
independent wide arithmetic. All sixteen coefficient codes match. Callee-saved
registers are randomized on structured cases and sampled exhaustive cases;
r1 is checked on all 4223904 ASM-firmware primitive returns. With ASM off,
GCC folds the selected and explicit C wrappers to the same address.

The isolated selected ASM wrapper is always 24 cycles / 2 MULs, versus
70..73 / 5 for the original-expression wrapper (including coefficient<<7).
The inline body itself is 18 cycles; wrapper register moves/RET account for
the remainder. Existing production code can hoist the coefficient shift, so
these wrapper savings must not be reported as complete-caller savings.
The narrowed coefficient wrapper is 17 cycles / 2 MULs versus 154 / 5.
Explicit C Q6 remains exact but its wrapper takes 88..91 cycles on this MCU.

[Arithmetic and fallback](../../Codecs/Speex/AVR/src/forced_math.h),
[fixture](../../Codecs/Speex/AVR/tests/avr_forced_math.c),
[builder](../../Codecs/Speex/AVR/tests/build_forced_math.py),
[exhaustive verifier](../../Codecs/Speex/AVR/tests/verify_forced_math.mjs).
Retained reports are `Codecs/Speex/AVR/reports/forced-math-unit-{asm,c}.json`.
Build with `--avr-gcc`; run the verifier on `build/forced-math-unit/asm` and
`build/forced-math-unit/c`. Only isolated C arithmetic executes, never the C
decoder.

The combined complete-image stage saves about 374 cycles per speech frame,
0.117 CPU percentage points, and 88 B bare Flash without increasing static
SRAM or peak stack. Full raw, +3%-load WB IRQ and actual SPI remain exact with
zero underruns. WB SPI minimum queue grows 31 -> 33 samples. Zero-coefficient
frames cost five extra caller cycles, included in the measured totals. NB1's
coefficient caller is unchanged; its 0..64 domain is preserved for later reuse.
[Exact workload, variant comparison and admission](../../Codecs/Speex/AVR/WB_FORCED_MATH.md).
