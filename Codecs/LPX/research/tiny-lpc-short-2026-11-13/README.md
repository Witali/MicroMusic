# Short LPC multiplication on ATtiny88

When the signed history high byte `H` is in `[-8,7]`, the AVR25 synthesis
loop accumulates `uint16(a)*H` into the partial product from the history
low byte. The range test already leaves `(H+8) mod 256` in `r22`. One
`subi r22,8` restores `H` and sets the zero and negative flags. Reuse those
flags for dispatch and send zero and the completed positive loop through
the same jump. Both accumulator loops keep their original 24-bit carry
chains and exact Q12 floors. The new code uses the existing registers.

Direct grouping of additions or subtractions was screened separately. On
the three initial controls, doubling the coefficient for an even positive
count reduced the addition count but cost 42–52 bytes. Pairing negative
subtractions cost 6 bytes. Moving the short block after the full-width
one saved 4 bytes but slowed five of the 22 measured loads by 0.44–0.57
cycles per sample. The selected code removes dispatch work and retains
the original number of accumulator additions and subtractions.

## Matched results

The baseline is `26faf772`, built with the AVR GCC ABI and AVR-GCC 7.3.0
at `-Os -flto`. Both universal builds run in simavr 1.6 at 16 MHz and 8 kHz
with SRAM512, LPC2, MUL16 unroll 2, FIFO32/prefill24 and the 38-cycle IRQ.
Program Flash shrinks by 4 bytes in all 22 builds, to 5474–5475 bytes
excluding embedded audio. All 308,339 PWM samples match the baseline and
the native C reference. Nineteen loads speed up and three tie. The maximum
gain is 7.76 cycles per sample. The heaviest load improves from 1748.39 to
1742.39 cycles per sample, including the complete IRQ. Peak stack is 62
bytes and the queue never underruns. The nine fixed-header website images
also rebuild byte for byte at their catalog gains.

A separate simavr run compared the assembly against the C product and
floor on all signed16 history values with eight coefficients, including
both signed endpoints. All 524,288 comparisons passed with 7,973 Timer1
interrupts. The compiler must identify AVR25 without MUL, and
`LPX4_ENABLE_ASM=1` explicitly enables assembly. The C backend remains
available on AVR25 with `LPX4_ENABLE_ASM=0`. This assembly is original
project work. [Measurements](measurements.json).

From the repository root, run the matched playback check in a fresh ignored
directory. On Windows with the toolchain in Ubuntu WSL, run:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-lpc-short --target tiny --baseline 26faf772 --wsl Ubuntu
```
