# Reuse neighboring coefficients in the Tiny88 LSF converter

The descending polynomial recurrence updates `p[j]` from the old values
`p[j-2]`, `p[j-1]` and `p[j]`. In the next iteration the old `p[j-2]`
becomes the multiply operand. Keep it in a local variable and seed the
first operand from the coefficient already loaded to initialize the edge
of P or Q. Each interior iteration reads two words from the ring instead
of three. Compute the product before loading the other two words to
reduce how long their values occupy registers. The addition order and
individual Q12 floors stay exact, including the wide product case.

The loop advances by four bytes with uint8 offsets. The offsets wrap
modulo 256 before forming the pointer. The aligned base keeps each
four-byte access inside the ring, and the existing `memcpy` accesses byte
storage directly. This C++ change applies to SRAM512 with the explicitly
enabled AVR25 ASM backend and runtime speech profile selection. The
original C recurrence remains selectable with `LPX4_ENABLE_ASM=0`.

## Matched playback

The baseline is `b4a97573`. Both builds use AVR-GCC 7.3.0 with the AVR GCC
ABI at `-Os -flto`, SRAM512, LPC2, MUL16 unroll 2 and FIFO32/prefill24.
simavr 1.6 runs the images at 16 MHz and 8 kHz with the complete 38-cycle IRQ.
The reported mean adds the full IRQ to the active decoder CPU mean.

On the Chego P4 ELF, `convertLsfAt` shrinks from 1214 to 1166 bytes. Each
of the 22 images saves 48 Flash bytes. Program Flash excluding embedded
audio drops from 5456–5457 to 5408–5409 bytes. All 308,339 PWM samples match
the baseline and the native C reference. Twenty-one loads speed up by
1.59–6.76 cycles per sample and one ties. The heaviest load improves from
1727.43 to 1720.77 cycles per sample with IRQ. Peak stack falls from 62 to
57 bytes, minimum queue depth rises from 19 to 20 samples and no underruns
occur. The nine fixed-header catalog images rebuild byte for byte at their
catalog gains. [Per-load measurements](measurements.json).

The independent full-convolution oracle with UBSan checks 368,640
conversions across LPC1/2/4, profiles 4/6/15 and every ring cursor. It also
checks the 145 live history slots. The native probe enables the new C++
loop in a private copy with C arithmetic. The actual Tiny88 player runs
the new loop under IRQ. A two-coefficient variant saved 12 Flash bytes
on controls and raised peak stack from 62 to 66 bytes.

Run the paired playback check from the repository root in a fresh ignored
directory. With the AVR toolchain installed in Ubuntu WSL, run:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-lsf-neighbors --target tiny --baseline b4a97573 --wsl Ubuntu
```
