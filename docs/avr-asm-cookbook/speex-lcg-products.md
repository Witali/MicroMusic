# Reuse products in a constant 32-bit LCG

Original project arithmetic optimization for classic AVR5 hardware MUL,
ATmega328P / 16 MHz, GNU ABI and AVR GCC 7.3.0. The recurrence and provenance
come from pinned Xiph Speex 1.2.1; BSD terms remain in its vendored COPYING.
The working [header](../../Codecs/Speex/AVR/src/lowrate_rng.h) includes an
explicit unsigned C fallback and uses ASM only with the supported architecture
and the separate ASM-enable define. Memory access is unaffected.

For `A=1664525=13+102*256+25*65536`, keep only byte products contributing below
bit 32. A general 32-bit product has ten such terms. Its zero top constant
byte removes one. Reuse `25*x=2*(13*x)-x` for the first two seed bytes to
remove another two MULs. For the lowest byte, initialize the result's upper
word with `25*x0` instead of zeroing it and adding that contribution later.
For the next byte, only the low byte of `25*x1` matters at bit 24.

This leaves seven MULs, with every carry and modulo-32 truncation preserved.
Initializing a future accumulator contribution avoids paying separately for
both its clear and its first add. Pass factors as read-only register operands
so a loop caller can hoist constant loads. Declare early-clobber outputs and
r0/r1/r2/condition-code clobbers; clear r1 before returning to compiled code.

Measured three-stream/384-frame WB3.95 screen, same Os/O2/O3/LTO/mrelax flags:
mean 269031.878 -> 257745.846 cycles, Flash 24750 -> 24804 B, static SRAM
1288 B unchanged, peak stack 211 -> 210 B. The intermediate nine-MUL variants
were slower. These are exact arithmetic improvements, not fewer-precision
samples or a new noise sequence. See the [full admission](../../Codecs/Speex/AVR/WB_NOISE_SPEED.md).

The isolated primitive checks 135243 seeds (every low/high word, boundaries,
random cases), C/ASM equivalence, actual ten-to-seven hardware MUL counts and
arbitrary callee-saved register patterns. Real-time support additionally needs
the complete active-IRQ/PWM and SPI checks linked above. A reduced MUL count
alone is insufficient: extra shifts/subtracts can otherwise make it slower.
