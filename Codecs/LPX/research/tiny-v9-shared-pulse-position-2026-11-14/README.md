# Share the compact P4 and Sparse80 pulse position mapping

Both parsers place four coded pulse positions into five consecutive sample
slots, skipping the middle slot. One function owns the mapping. For
`code` in 0..63, `(code+2)>>2` is `code>>2` plus the original bit 1. Two
logical right shifts leave that bit in carry on AVR25. An `ADC` then adds
the quotient and carry to the unmodified code. The short sequence inlines
at both call sites. The selectable C version uses the original expression.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, LPC2, MUL16 unroll 2 and FIFO32/prefill24. Compared with
`974942f`, the program shrinks by 24 B to 4874–4875 B excluding the identical
audio. At 16 MHz and 8 kHz all 22 simavr 1.6 loads reproduce the baseline
and independent C PWM for all 308,339 samples, with zero underruns. Mean
decoder CPU time plus IRQ drops by up to 0.295 cycles/sample. Peak stack
stays at 53 B and peak decode cost does not increase. All 18 published
WebUI images rebuild byte for byte.

The outlined C mapping saved 12 B and added up to 0.450 cycles/sample in
the same matrix. The shared AVR carry version removes that overhead.
[Per-load measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/pulse-position-matched --target tiny --baseline 974942f
```
