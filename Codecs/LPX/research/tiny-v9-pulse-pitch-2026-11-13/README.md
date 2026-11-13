# Compact the Tiny88 LPX v9 excitation path

Baseline `65c3073e`. ATtiny88 / AVR25, AVR-GCC 7.3.0 with the GNU AVR ABI,
`-Os -flto`, SRAM512, two LPC segments, MUL16 unroll 2, FIFO32/prefill24.
The player runs at 16 MHz and outputs at 8 kHz. Program Flash includes the
player and lookup tables and excludes the exact embedded LPX file.

The universal compact v9 build with explicit AVR25 ASM uses one pitch path.
It only clips the quantized code when adding an innovation. Without a
pulse, the prediction already fits −28..27. The pulse-gap countdown and
history write retain their order. Parsing checks errors before synthesis.

Compact pitch gain equals twice a three-bit value. Rewriting Q4
`(x*gain+8)>>4` as Q3 `(x*(gain/2)+4)>>3` preserves the signed floor.
The existing AVR25 shift-and-add kernel consumes three multiplier bits
and subtracts the sign bias from the low byte of the quotient. C remains
selectable through `LPX4_ENABLE_ASM=0`, using the existing calculation.

## Measurements

| Measurement | Baseline | Final |
| --- | ---: | ---: |
| Program Flash, bytes | 5408–5409 | 5360–5361 |
| Highest workload mean with complete IRQ, cycles per sample | 1720.77 | 1664.87 |
| Peak stack, bytes | 57 | 56 |
| Minimum queue depth, samples | 20 | 23 |

All 308,339 PWM samples match across 22 P4, P6 and sparse80 workloads.
The simavr 1.6 observer confirms normal completion, zero underruns and
38 cycles for the complete IRQ. Speed improves by 38.47–60.30 cycles per
sample, measured as mean active decoder CPU plus the full IRQ. All 18
published Tiny88 and Nano images rebuild byte for byte. The direct AVR25
arithmetic probe checks all 2048 combinations of signed history byte
and legal even gain with IRQ active. [Per-workload results](measurements.json).

Outlining the 20-sample boundary saves 64 bytes by itself and increases
the peak stack by 9 bytes. The tested 24-bit C++ polynomial representation
with padded four-byte slots adds 20 Flash bytes. Both experiments stay
outside the production path.

From the repository root, build and measure the current code and the
baseline in an ignored directory with AVR-GCC 7.3.0, g++ and simavr 1.6.
On Windows with the toolchain in Ubuntu WSL, add `--wsl Ubuntu`.

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-pulse-pitch --target tiny --baseline 65c3073e
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py build/tiny-pitch-domain --mul16-unroll 2 --saturated-products
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/tiny-pitch-domain
```
