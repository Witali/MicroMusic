# Shared Q14 postfilter on ATtiny88

Both runtime filters use the same AVR25 kernel to compute
`floor(coefficient * state / 16384)`. Bias the signed 16-bit state by 32768
with a high-byte `subi`, multiply the resulting unsigned value, then
subtract `2 * coefficient` from the quotient. The bias adds an integer
to the quotient, so the subtraction preserves the exact floor on the
entire signed16 domain.

The first coefficient bit selects zero or half the biased state. This
replaces an addition into the initially zero accumulator with `movw`.
The remaining rounds shift the original low and high coefficient bytes in
place. Each round performs `floor((accumulator + bit * biased_state) / 2)`,
and the carry into the rotation retains the 17th sum bit. The bounded
coefficient domain is 0–16384. Only the unity endpoint has bit 14 set, and
the half-scale case tests the two bytes before any multiplication.

The existing real AVR25 and explicit ASM selectors guard the new kernel.
`LPX4_ENABLE_ASM=0` selects the equivalent C on AVR25. The coefficient
and the state retain their original domains and the decoder still reads
the coefficients from the stream. This is original project assembly for
the AVR GCC ABI.

## Matched playback

The baseline is `dc522dea`. AVR-GCC 7.3.0 builds both revisions at
`-Os -flto`. simavr 1.6 runs the builds at 16 MHz and 8 kHz with SRAM512,
LPC2, MUL16 unroll 2, FIFO32/prefill24 and the 38-cycle IRQ. The time metric
is active decoder CPU mean plus one complete IRQ per sample.

The shared filter routine in the heavy ELF shrinks from 240 to 222 bytes.
Each of the 22 full images saves the same 18 bytes. Program Flash, excluding
embedded audio, goes from 5474–5475 to 5456–5457 bytes. All 308,339 PWM samples
match the baseline and the native C reference. Twenty loads speed up by
3–21 cycles per sample and two tie. The heaviest load goes from 1742.39 to
1727.43 cycles per sample with IRQ, and its minimum queue depth rises from
16 to 19 samples. Peak stack stays at 62 bytes and there are no underruns.
All nine fixed-header catalog images rebuild byte for byte at their existing
gains. [Measurements](measurements.json).

A separate simavr arithmetic run compares the selected ASM with the C
product and shift. It covers all 16,385 coefficients at eight boundary
states and every signed16 state at sixteen coefficients. All 1,179,656
comparisons pass, with 7,442 Timer1 interrupts. The six-round counted loop
for the high byte saves 54 program bytes on the initial controls but costs
26 cycles per sample on the heavy control. The final kernel keeps those
rounds unrolled.

Run the paired playback check from the repository root in a fresh ignored
directory. On Windows with the AVR toolchain in Ubuntu WSL, run:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-q14 --target tiny --baseline dc522dea --wsl Ubuntu
```
