# Interpolate LPC using an unsigned 16-bit fractional product

The AVR25 v9 decoder interpolates at odd subframe phases. The endpoint
difference may need 17 signed bits, and its magnitude fits in 16 bits.
The signed subtraction flags select the sign to restore. Start the
unsigned accumulator at half the magnitude for the guaranteed low phase
bit. For each higher bit, add the magnitude when the bit is set and
rotate the carry into the high byte during the right shift. Negating the
final quotient when required preserves truncation toward zero. The C
reference retains the signed product and exact bias before shifting.

For static spectra, subframe zero fills the cache and copies the endpoint.
The remaining subframes can return immediately in the compact build with
rotating anchors and no bandwidth expansion. The interpolation change
by itself added 0.05 cycles/sample in the all-pairs static control.
The early return removes that increase.

ATtiny88 at 16 MHz and 8 kHz using AVR-GCC 7.3.0, the GNU AVR ABI,
SRAM512, LPC2, MUL16 unroll2, FIFO32/prefill24 and
`-Os -flto -mcall-prologues -mrelax`. Compared with `62cbe883`,
the image saves 32 program bytes on each of the 22 IRQ-active workloads.
The program occupies 4708–4709 bytes excluding audio. The AVR arithmetic
probe checks phases of 2, 3 and 4 bits, including extreme endpoint pairs.
All 308,339 playback samples match the previous build and the C decoder.
Mean decoder time including IRQ drops by 0.300–5.796 cycles/sample.
The all-pairs control's largest single decode call takes one extra cycle
(13,127 to 13,128), with the same minimum queue of 27 samples.
Fourteen additional controls cover short tails, repeated playback and
malformed streams. Each drains the expected PWM prefix. All 18 release
images tracked at the baseline rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-unsigned-interp --target tiny --baseline 62cbe883
```
