# End AVR25 v9 pulse packets with an idle countdown

The last pulse advances to one more gap initialized to 127. The next
packet, or the end of playback, arrives within 80 samples. Decrementing
the idle countdown therefore cannot produce an innovation. This uses
the byte formerly reserved for the packet's pulse count. After a
`DEC` and `ST`, the AVR25 producer branches directly on N. The
explicit C backend detects the same zero-to-255 wrap. Pulse positions,
collision merging and amplitudes retain the existing LPX v9 semantics.

The paired comparison against `e1583321` uses AVR-GCC 7.3.0 with GNU
AVR ABI, ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. On all 22
simavr 1.6 workloads with active IRQ, the program saves 44 B to occupy
4506–4507 B excluding audio. Mean decoder CPU plus IRQ drops by
1.64–7.60 cycles per sample. The largest measured mean is 1624.04.
Every workload's highest single-call decoder CPU cost also decreases.

All 308,339 PWM samples match the baseline and portable C. The producer
retains at least 24 queued samples, with zero underruns, 433 B of static
SRAM and a 51 B stack peak. Fourteen additional IRQ cases cover repeated
playback, partial tails and rejected or truncated streams. Six direct
AVR25 cases match across baseline and candidate builds using ASM, C and
forced-generic backends. They cover the earliest and latest Sparse80
pulses, every Sparse80 position code, P4 and P6 extras, and truncation.
All 18 WebUI images rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-pulse-sentinel --target tiny --baseline e1583321
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-pulse-sentinel-web --run
```
