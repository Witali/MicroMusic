# LPX v9 fixed-register sample IRQ on ATmega328 and ATmega328P

Measured prototype for the single-playback 16 MHz AVR5 player at 8 kHz.
For the reserved-register trial, the adapted ROM player selected the
existing AVR25 naked ISR on AVR5. The build reserved `r2` and `r3` in
all foreground code with `-ffixed-r2 -ffixed-r3`. The ISR saves Z and
SREG, reads a byte from the FIFO and writes OCR1AL. The foreground
initializes OCR1A while interrupts are masked, then leaves the Timer1
high-byte latch available to the ISR. The test uses
`LPX25_REUSE_TIMER1_HIGH=1`. The handler leaves `r0` and `r1` untouched,
including interrupts during a MUL sequence with nonzero `r1`.

| ASM configuration | Program with player and tables, excluding audio | Largest mean decoder + IRQ cycles/sample | Complete IRQ | Peak stack |
| --- | ---: | ---: | ---: | ---: |
| Nine unrolled taps, ordinary C ISR | 5052–5053 B | 829.04 | 64 | 67 B |
| Nine unrolled taps, reserved-register ASM ISR | 4868–4869 B | 784.06 | 39 | 51 B |
| One tap per iteration, reserved-register ASM ISR | 4440–4441 B | 820.06 | 39 | 51 B |

Each of the three configurations produced the same PWM on four workloads
per target, 42,293 samples, with zero underruns. ATmega328 and ATmega328P
both used their real `-mmcu` settings and matched the observed hardware
constants. The observer checked MUL scratch registers at IRQ return.
The full unroll with a shorter IRQ saves 184 B and 42.45–44.98 cycles
per sample versus the ordinary ISR. The one-tap loop adds 36 cycles per
sample versus the same optimized IRQ with full unrolling.

AVR-GCC 7.3.0, GNU AVR ABI, simavr 1.6, SRAM512, FIFO32 prefilled with 24
samples, two LPC segments. The size recipe includes `-Os -flto
-mcall-prologues -mrelax -finline-small-functions`. The four workloads
are Chego compact, quality and 2 kb/s, plus changing sparse80 with lag 18,
pre-emphasis 16383 and brightness 11468. This is a simulator experiment
with the alternate ISR selected in a scratch build.
