# Divide only the proven numerator bits

For classic AVR5 with hardware MUL and GNU ABI, a bounded positive division
can be cheaper than generic signed32 division without using an approximate
reciprocal. First prove the rounded numerator's range and the divisor's sign.

The Speex HB1 energy table has 32 values <=904448 and a validated divisor
1..32767. Its original rounding gives a numerator <=920831 (<2^20). Split
this into a small high word and sixteen low bits. Repeated subtraction divides
the high word (at most thirteen subtractions); sixteen restoring-division
steps then produce the remaining quotient. At every step `r < d <=32767`, so
`2*r+bit <=65533`: the remainder needs only sixteen bits. These bounds are
specific to this caller and must not be assumed for generic integer division.

Reusable [GNU AVR routine](../../Codecs/Speex/AVR/src/wb_gain_div.S),
[selectable C expression](../../Codecs/Speex/AVR/src/wb_gain_div.h).
The routine uses only call-clobbered r18..26 and flags, preserves r1 and
callee-saved registers, and neither allocates local stack nor masks interrupts.
Use the project's architecture selector plus explicit ASM enable; default C.
Flash memory access remains in the caller.

Measured with AVR GCC 7.3.0, existing Os/O2/O3, LTO/mcall-prologues/mrelax,
avr8js 0.21.1. Exhaustive 32 x 32767 caller-domain tests and 516 boundaries
match independent BigInt and scalar AVR C, including arbitrary callee-saved
register patterns. The leaf is 62 B and takes 194..322 cycles including RET.
A matched 384-frame WB3.95 screen saves 1647.63 cycles/frame (0.677%); whole
decoder Flash grows 8 B, static SRAM/peak stack stay unchanged. Screen PCM
and reset are exact. This is not yet a full-output/physical-board admission.
See [bounds, workload and reproduction](../../Codecs/Speex/AVR/WB_GAIN_DIV.md).

Original project technique; no external implementation copied. Preserve the
existing upstream table/algorithm licenses when reusing the surrounding codec.

The complete five-profile stage subsequently passes 106014 matched raw
frames, 53007 full-history IRQ frames and 5800 long SPI frames, all exact
PCM/PWM with zero underruns. Natural-speech frame time falls 0.67..0.70%
for eight additional Flash bytes, with unchanged bare SRAM/peak stack.
IRQ gates retain 8% extra work for WB3.95/9.8/12.8 and 3% for WB5.75/7.75;
SPI separately includes transport at zero extra load. C decoder images are
compiled/linked only; the scalar C fallback is exhaustively checked above.
