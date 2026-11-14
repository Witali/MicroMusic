# Rotate cached LPC endpoints directly on AVR25

The compact AVR25 v9 parser makes the initial frame static, including when
its LSF indices differ from the zeroed workspace. The static path computes
and caches the current endpoint before any later dynamic frame. At dynamic
segment boundaries the two anchors can always rotate, and the cache-valid
bit stays set. Other configurations retain the generic initialization path.

On ATtiny88 with the GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, LPC2, MUL16 unroll 2 and FIFO32/prefill24, the linked
program shrinks by 26 B to 4898–4899 B excluding audio. At 16 MHz and 8 kHz,
all 22 simavr IRQ workloads yield exact baseline and independent C PWM for
308,339 samples. There are zero underruns. Mean active decoder CPU time plus
IRQ improves by up to 0.069 cycles/sample on 21 loads, with one tie. Peak
stack stays at 53 B and minimum queue occupancy matches on every load.
All 18 WebUI binaries rebuild byte for byte.
[Paired measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/anchor-rotate-matched --target tiny --baseline 38df1396
```
