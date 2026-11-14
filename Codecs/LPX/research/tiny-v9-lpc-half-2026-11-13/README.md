# Halve and clip the final LPC coefficients in 24 bits on Tiny88

Baseline `c415ab84`. ATtiny88 / AVR25, AVR-GCC 7.3.0, GNU AVR ABI,
`-Os -flto -mcall-prologues -mrelax`, SRAM512, LPC2, MUL16 unroll 2
and FIFO32/prefill24. Measurements use simavr 1.6 at 16 MHz and 8 kHz.
Each pair embeds the same compressed stream.

The degree-11 polynomial coefficient bound is
`4096*binomial(11,5)+1`. The extra unit accounts for the two floors in
the last guarded product. The sum of a P and Q coefficient therefore
fits signed24. The universal AVR25 v9 decoder adds one to a negative
sum, shifts three bytes right and then reuses the signed24 clip.
The C path preserves the same truncation toward zero and clamp to
`[-32767,32767]`.

The complete program shrinks by 8 B on all 22 workloads to 5190–5191 B
excluding audio. All 308,339 PWM samples match the C decoder with IRQ
active. There are no underruns and peak stack stays at 54 B. The mean
decoder CPU time plus IRQ improves by 0.13–0.65 cycles per sample on 21
workloads and ties on one. The largest workload mean falls from
1656.30 to 1655.78. Every workload's peak decoder CPU time per call
falls by 83–97 cycles.
[Per-workload measurements](measurements.json).

The AVR arithmetic probe checks both signed24 input endpoints, odd
negative rounding, both clipping edges and deterministic random values
on C, ASM and forced generic with IRQs active. All 18 existing WebUI
images rebuild byte for byte.

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/lpc-half-matched --target tiny --baseline c415ab84 --wsl Ubuntu
```
