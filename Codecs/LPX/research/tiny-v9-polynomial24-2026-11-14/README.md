# Keep the shared LPC polynomial recurrence in signed 24 bits

Through degree nine every coefficient is bounded by 4096 times the
corresponding binomial coefficient. Each quadratic factor is bounded by
`1 + 2z + z²`. At the last factor the separately rounded wide product can
add at most one unit to the magnitude bound. Every intermediate sum in the
descending recurrence fits signed24, as does the final sum of P and Q.
The AVR25 recurrence loads three bytes per aligned four-byte ring slot and
reuses the previous multiply operand when stepping back. The original
selectable C recurrence retains its signed32 storage and rounding.

The paired build uses ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, SRAM512, two LPC segments, MUL16
unroll 2 and FIFO32/prefill24. In simavr 1.6 at 16 MHz and 8 kHz all 22
IRQ-active loads yield bit-exact PWM for 308,339 samples, with zero
underruns. Compared with `1161c7ea`, the program shrinks by 12 B to
4858–4859 B excluding audio. The mean decoder CPU time plus IRQ falls by up
to 2.137 cycles/sample, with one tie. Peak decode CPU time falls by 313–345
cycles on every load. Stack stays at 53 B and min queue never decreases.
All 18 published WebUI images rebuild byte for byte.

The host oracle uses the same descending recurrence with explicit
three-byte loads and stores, UBSan and a signed24 range assertion.
The independent full polynomial matches all 368,640 conversions at all
256 ring cursors with 1, 2 and 4 LPC segments. The 145 live history bytes
remain intact. [Paired IRQ measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/poly24-matched --target tiny --baseline 1161c7ea
```
