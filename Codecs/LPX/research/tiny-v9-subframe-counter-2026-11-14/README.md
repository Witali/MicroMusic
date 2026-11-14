# Advance the AVR25 subframe counter once per 20 samples

In the compact v9 runtime, the low three bits already identify the subframe
within its half. Bit 3 can directly identify the half if the byte increments
once per subframe. The frame reader then tests bit 3 without writing it.
Bits 4–7 have no consumers in this configuration. The selectable C reader
and other builds retain the original counter updates.

In the ATtiny88 GNU AVR ABI build with AVR-GCC 7.3.0, `-Os -flto
-mcall-prologues -mrelax`, SRAM512, LPC2, MUL16 unroll 2 and FIFO32/prefill24,
the linked program uses 16 B less Flash than `0c1113fa` and occupies
4842–4843 B excluding audio. On simavr 1.6 at 16 MHz and 8 kHz, all 22
IRQ-active loads give exact baseline and independent C PWM for 308,339
samples. Every load saves 0.224–0.238 decoder CPU cycles per sample
including IRQ. Peak decode cost falls by 4–6 cycles. Stack stays at 53 B
and all workloads play to completion with zero underruns.

Three additional complete IRQ playbacks exercise repeated byte wrap with
32,000 P4, 25,600 P6 and 64,000 Sparse80 samples. All match the independent
C decoder. All 18 published WebUI images rebuild byte for byte.
[Paired IRQ measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/free-subframe-counter-matched --target tiny --baseline 0c1113fa
```
