# Advance the bounded LPX cursor with LPM on AVR25

The AVR25 ROM reader uses `LPM Rd,Z+` to load and advance the pointer in
one instruction. The C reader uses the existing device-header access macro.
The byte-limit check, error handling, and callback path retain their order.
The optimized instruction is guarded by the explicit ASM backend and v9
runtime profile.

ATtiny88 at 16 MHz and 8 kHz, AVR-GCC 7.3.0 with GNU AVR ABI,
`-Os -flto -mcall-prologues -mrelax`, SRAM512, LPC2, MUL16 unroll2,
FIFO32/prefill24. Compared with `bd3ec1ce`, all 22 program images save 4 B
and retain the identical compressed stream. With simavr 1.6 and active
IRQ, all 308,339 PWM samples match both the earlier firmware and the C
reference. Decoder CPU time including IRQ falls by 0.058–0.340 cycles/sample
and there are zero underruns.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-flash-read --target tiny --baseline bd3ec1ce
```
