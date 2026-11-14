# Move subframe preparation out of the Tiny88 sample loop

Baseline `9760ff7f`. ATtiny88 / AVR25 without hardware MUL, GNU AVR ABI,
AVR-GCC 7.3.0 at `-Os -flto -mcall-prologues -mrelax`, SRAM512, LPC2,
MUL16 unroll 2 and FIFO32/prefill24. simavr 1.6 runs at 16 MHz with an
8 kHz sample rate. Flash measurements include player code and tables.
Each pair embeds the same LPX bytes.

The decoder calls `prepareSubframe` only at the start of a subframe,
after checking the sample bounds. It preserves the order of frame and
pulse parsing, LPC interpolation and optional bandwidth expansion.
AVR25 universal v9 builds with explicit ASM outline the helper. The
selectable C decoder inlines the same implementation.

The standalone player's `main` starts with interrupts masked and never
returns. AVR-GCC's `OS_main` attribute omits saving the caller's
callee-saved registers in that entry point. Subroutines still follow the
ordinary AVR ABI. The attribute is selected for the same universal v9
AVR25 build. [GCC AVR function attributes](https://gcc.gnu.org/onlinedocs/gcc-8.5.0/gcc/AVR-Function-Attributes.html).

| Measurement | Before | After |
| --- | ---: | ---: |
| Program Flash excluding audio, bytes | 5270–5271 | 5238–5239 |
| Highest workload mean with IRQ, cycles per sample | 1664.36 | 1659.53 |
| Peak stack, bytes | 60 | 54 |
| Minimum stack margin, bytes | 18 | 24 |
| Minimum queue depth, samples | 23 | 23 |

All 308,339 PWM outputs across 22 loads match the reference C decoder.
The 38-cycle IRQ completes with zero underruns. Every workload saves
2.91–5.21 cycles per sample in mean active decoder CPU plus IRQ.
All 18 published WebUI images rebuild byte for byte.
[Per-load measurements](measurements.json).

On four control loads, outlining alone saves 22 Flash bytes and raises
stack usage by 10 bytes. The entry attribute alone saves 2 Flash bytes
and 16 stack bytes. Both effects depend on the linked image and AVR-GCC
register allocation.

Run the matched tests with AVR-GCC, g++ and simavr 1.6. On Linux omit
`--wsl Ubuntu`.

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/subframe-matched --target tiny --baseline 9760ff7f --wsl Ubuntu
```
