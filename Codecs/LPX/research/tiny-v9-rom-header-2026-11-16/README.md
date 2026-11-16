# Load LPX v9 header words directly from Flash on AVR25

The universal ATtiny88 decoder validates the 13-byte input bound, magic
and flags before copying the five little-endian header words. The copy
includes the payload length and leaves Z at the payload. The decoder checks
the copied length against the supplied input size before using it. AVR
offset assertions guard the layout. The selectable C reader and ASM
reader share acceptance rules. All recording parameters stay in the LPX
stream.

The paired comparison uses `cef91038`, AVR-GCC 7.3.0 with GNU AVR ABI,
ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. In simavr 1.6
all 22 full IRQ workloads save 66 program bytes, down to 4574–4575 B
excluding the embedded LPX. Mean decoder CPU plus IRQ falls by 0.525–2.956
cycles per sample. The largest measured mean is 1627.07 cycles. The highest
cost of a single decoder call in each workload falls by 285–468 cycles.
First output arrives 741–879 cycles sooner.

All 308,339 PWM samples match the previous build and a portable C oracle.
The observed stack peak is 51 B with 433 B of static SRAM. The minimum
queue occupancy during production is 24 samples, with zero underruns.
Fourteen further IRQ controls cover short tails, repeated playback and
truncation. A 295-case AVR25 header probe covers all 256 flag values
and malformed headers in ASM, C, forced-generic, unbatched and indexed
reader builds against the baseline and expected API results. Eighteen
public WebUI images rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-rom-header --target tiny --baseline cef91038
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-rom-header-web --run
```
