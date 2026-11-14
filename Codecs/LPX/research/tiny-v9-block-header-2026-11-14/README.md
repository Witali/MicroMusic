# Read the compact block scale and gain together on AVR25

LPX v9 stores a five-bit scale followed by a three-bit gain, LSB first.
One eight-bit read yields the same fields at any bit alignment. The lag is
read only when gain is nonzero. For the Q4 synthesis configuration, the
32-entry table stores each original scale multiplied by 16. Its maximum is
47,456, which fits uint16. The selectable C parser retains separate reads
and scaling. The compressed bytes, filters and quantization are unchanged.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, two LPC segments, MUL16 unroll 2 and FIFO32/prefill24.
Compared with `ab6eb68d`, program Flash shrinks by 10 B to 5024–5025 B
excluding audio. In simavr 1.6 at 16 MHz and 8 kHz, all 22 workloads match
the baseline and independent C PWM. All 308,339 samples play with zero
underruns. Mean active decoder time plus IRQ decreases by 0.19–0.38
cycles/sample. Peak decode CPU time falls by 59–64 cycles on every workload.
Peak stack, static SRAM and minimum queue occupancy are unchanged.
All 18 WebUI images rebuild byte for byte.
[Paired measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/gain-q4-matched --target tiny --baseline ab6eb68d
```
