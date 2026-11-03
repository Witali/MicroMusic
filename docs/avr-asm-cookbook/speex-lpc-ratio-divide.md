# Use saturation to shorten an exact division

Measured target: ATmega328P / classic AVR5, GNU ABI, AVR GCC 7.3.0,
avr8js 0.21.1. This entry concerns an isolated scalar kernel's speed and size.
It does not establish complete decoder throughput, output queue margin,
transport latency, analog quality or physical-board operation.

The HB1 LPC-response ratio is a rounded signed32 division followed by
saturation to signed16 magnitude 32767. Its caller validates positive
responses before division. Let `a = rl + 82` and `d = rh + 82`. Ten low-band
and eight high-band signed16 coefficients give these independent bounds:

```text
a = 8274 + sum(5 coefficient differences) <= 8274 + 5*65535 = 335949
d = 8274 + sum(4 coefficient differences) <= 8274 + 4*65535 = 270414
1 <= a <= 335949; 1 <= d <= 270414
n = a*128 + ((int16_t)d >> 1): -16256 .. 43017855
```

The cast before the half-divisor shift is part of Xiph's `PDIV32` semantics.
For example, divisor 32768 contributes -16384, rather than +16384. Preserve
that cast and division toward zero. If `n` is negative, the half term must
be negative, hence `d >= 32768`; `abs(n) <= 16256 < d`, so the original
quotient is exactly zero. No negative quotient can occur in this domain.
These are coefficient-width bounds, not assumptions about typical speech,
filter stability or codebook distributions.

For nonnegative `n`, retain the upper remainder `r = n >> 15`, at most 1312.
If `r >= d`, the quotient is at least 32768 and its saturated result is
already known: 32767. Otherwise process just the remaining fifteen numerator
bits with restoring division. Before each step `r < d`, so after shifting
`2*r + bit <= 2*d - 1 <= 540827`. A 24-bit remainder is sufficient; the
exact quotient fits fifteen bits. An unsaturated generic signed32 quotient
would perform unnecessary high-bit work.

The [GNU AVR leaf](../../Codecs/Speex/AVR/src/wb_gain_div.S) uses two registers
for the low numerator/quotient, three for the remainder, three for the divisor
and one loop counter. It uses only call-clobbered registers, preserves r1 and
all callee-saved registers, and adds no memory accesses, local stack, persistent
state or interrupt masking. The existing HB1 energy divider remains a separate
entry in the same source file; it has different operand bounds.

The [C equivalent and selection](../../Codecs/Speex/AVR/src/wb_gain_div.h)
retain the original cast, rounding, division and saturation. Assembly requires
the existing supported architecture/ABI checks **and** explicit
`SPEEX_NB3_ENABLE_ASM=1`. Setting it to zero on AVR selects C; a forced generic
arithmetic architecture also selects C while retaining the compiler's real
CPU macros. Hardware memory access is independent of this arithmetic choice.
Neither entry is a general divide API: positivity and bounds belong to the
private caller contract.

The assembled leaf is **72 B**, with no table or persistent RAM. Measured
entry-through-RET time is **9..257 cycles**, excluding caller rounding,
interrupt instructions and interrupt entry. The regular fifteen-step path's
instruction count is `212 + 3*popcount(quotient)` cycles, or 212..257;
negative-numerator and initial-saturation returns take 9 and 19 cycles.
The isolated original-expression O3 C wrapper takes 660..707 cycles, including
its rounding, saturation and prologue/epilogue. Those boundaries differ from
the raw ASM leaf, so their ratio is not a whole-decoder speedup. Final program
Flash also depends on inlining, register allocation and shared helper removal.

Both full bare and full active-Timer2 runs check **824573 pairs** against
independent BigInt arithmetic and isolated AVR C: every divisor 1..270414
with responses 1/8192/335949, 3331 boundary cases and 10000 coefficient-derived
pairs. They include 130103 negative rounded numerators and saturation/zero
boundaries. Each full run checks 1649146 ASM returns with arbitrary callee-saved
patterns and zero r1, read-only operands, and selected/explicit C paths.
This sweep exhausts the divisor range, not every pair in the large response
rectangle; the derivation establishes the arithmetic domain separately.

The full IRQ run completes **2575903 timer compare events and interrupts**,
with an independent check of the ISR's multiplication accumulator and no
lost interrupts. Timer2 uses a 64-count CTC period and divide-by-eight clock;
its 512-cycle interrupt period stresses preemption independently of audio.
All register addresses and vector spacing come from the pinned `avr/io.h`
device definitions. Maximum fixture stack is 12 B bare / 24 B with IRQs;
this includes callers/ISR and is not decoder stack usage. Explicit C and
forced-generic fixtures each pass 4403 IRQ pairs and 18451 interrupts, and
their firmware binaries are identical. No complete C decoder executes.

```sh
python Codecs/Speex/AVR/tests/build_wb_ratio.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_wb_ratio.mjs Codecs/Speex/AVR/build/wb-ratio-unit/asm
node Codecs/Speex/AVR/tests/verify_wb_ratio.mjs Codecs/Speex/AVR/build/wb-ratio-unit/asm --irq
node Codecs/Speex/AVR/tests/verify_wb_ratio.mjs Codecs/Speex/AVR/build/wb-ratio-unit/c --quick --irq
node Codecs/Speex/AVR/tests/verify_wb_ratio.mjs Codecs/Speex/AVR/build/wb-ratio-unit/generic --quick --irq
python Codecs/Speex/AVR/tests/audit_wb_ratio.py
python Codecs/Speex/AVR/tests/audit_wb_ratio.py --check
```

The builder uses `-Os -flto -mcall-prologues -mrelax -fwrapv
-fno-strict-aliasing`, C11 and the existing O3 scalar wrapper attribute.
Its inputs bind compiler/subtool and device-header hashes. The compact
[receipt](../../Codecs/Speex/AVR/reports/wb-ratio-unit.json) binds the kernel,
test/audit tools, simulator lock and raw reports without host paths or media.
Source hashes normalize UTF-8 text to LF so a CRLF checkout preserves evidence;
external compiler/subtool and device-header hashes retain exact bytes.
`audit_wb_ratio.py --rebind-source-metadata` migrates earlier source-byte
metadata only when the binary matches and each source hash proves equivalent
LF/CRLF text. It changes neither binary bytes nor runtime results. The receipt
states that metadata conversion explicitly. Generated binaries/logs remain ignored.

The saturation-domain reduction and assembly are original project work.
Preserve the surrounding [Xiph fixed-point semantics](../../Codecs/Speex/AVR/vendor/speex-1.2.1/libspeex/fixed_generic.h)
and [Speex 1.2.1 BSD notice](../../Codecs/Speex/AVR/vendor/speex-1.2.1/COPYING)
when reusing the codec. No approximate reciprocal or synthesis change is used.
