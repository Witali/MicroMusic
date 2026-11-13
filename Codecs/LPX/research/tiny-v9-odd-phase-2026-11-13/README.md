# Use the odd LPC interpolation phase on Tiny88

Baseline `70317424`. ATtiny88 / AVR25, AVR-GCC 7.3.0 and GNU AVR ABI,
`-Os -flto -mcall-prologues -mrelax`, SRAM512, LPC2, MUL16 unroll 2
and FIFO32/prefill24. Measurements use simavr 1.6 at 16 MHz and 8 kHz.
The compared images embed the same audio bytes.

The interpolation phase is `(2*sub+1) % width`. The width is 4, 8 or 16,
so the phase is odd and smaller than the width. Start the accumulator
at the signed17 delta and add the truncation bias before processing the
remaining bits. Only negative deltas need `width-1` added. All biased
products fit signed24. The compiler selects this path for the explicitly
enabled universal LPX v9 AVR25 backend. C evaluates the same integer formula.

On all 22 IRQ workloads the linked program shrinks by 40 B to 5198–5199 B,
excluding the embedded audio. The full 308,339 PWM bytes match the
C-verified baseline. There are no underruns and peak stack stays at
54 B. Mean active decoder CPU plus the complete IRQ improves by
0.77–3.28 cycles per sample on 21 loads and ties on one. The maximum
workload mean falls from 1659.53 to 1656.30 cycles per sample.
Peak decoder CPU cycles for a single call fall by 230 in those same
21 workloads and tie on the remaining workload. All 18 WebUI binaries
rebuild byte for byte. [Measurements](measurements.json).

The AVR arithmetic test adds 5,246 odd-phase cases per backend. It
checks every legal odd phase for the boundary coefficient pairs plus
deterministic random signed16 pairs on C, ASM and forced generic,
with IRQs active and ABI checks.

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/odd-phase --target tiny --baseline 70317424 --wsl Ubuntu
```
