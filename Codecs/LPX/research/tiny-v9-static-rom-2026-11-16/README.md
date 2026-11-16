# Reuse static zero initialization for the Tiny88 ROM decoder

The one-shot AVR25 v9 player owns one static decoder object. AVR startup
clears its entire BSS storage. The player uses a private constructor for
that zero-initialized instance. All ordinary instances continue to use
the public constructor. The normal `begin()` reset is still called for
the first stream and every replay.

AVR-GCC 7.3.0 with the GNU AVR ABI can omit the global constructor table,
its walk, and the redundant member initialization. The same binary
recipe uses 16 MHz, 8 kHz, AVR25, LPC2, SRAM512, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`.

The matched build compares against `424d6111` with active IRQ in simavr 1.6.
All 22 images save 68 program bytes and occupy 4640–4641 B excluding
audio. The first PWM output arrives 2,122 cycles earlier on each load.
Mean and peak decoder time, IRQ timing, stack and queue occupancy match
the baseline. All 308,339 PWM samples agree with both the previous image
and an independent C decoder. Fourteen additional cases exercise malformed
inputs, short tails, and replay. P4, P6 and Sparse80 cold-start controls
also fill all simulated SRAM with `0xa5` before AVR startup. All three
produce the expected PWM. All 18 previous WebUI images rebuild byte for
byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-static-rom --target tiny --baseline 424d6111
```
