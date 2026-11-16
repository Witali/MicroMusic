# Address AVR25 v9 cosine factors from the zero node

The exact half-grid ends at zero, node 64. Subtract twice the absolute
distance from 64 to address its reflected word. T retains the sign of
the original difference while the routine calculates Z and loads the
word. This produces the required negative cosine factor directly from
the existing table. The selectable C backend uses the ordinary
lookup. All 129 node indices match it in AVR execution with both
incoming T values, for 258 exact checks.

The paired comparison against `833a2ad0` uses AVR-GCC 7.3.0 with GNU AVR
ABI, ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. All 22 full
simavr 1.6 IRQ workloads save 12 program bytes to occupy 4470–4471 B
excluding the embedded LPX. Mean decoder CPU plus IRQ falls by up to
0.319 cycles per sample. The largest measured mean is 1623.54.

All 308,339 PWM samples match the previous build and portable C. The
producer keeps at least 24 queued samples, with zero underruns and a
50 B peak stack. Eighteen WebUI images rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-cos-edge --target tiny --baseline 833a2ad0
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-cos-edge-web --run
```
