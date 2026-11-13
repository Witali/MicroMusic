# ATtiny88 LPC multiplication in pairs of bits

The full-width branch of the LPC synthesis loop already has
`floor(uint16(a) * lo(h) / 256)` after processing the history low byte.
The new branch initializes `r23` with the history high byte. The initial
`lsr` puts its first bit in carry. Each conditional addition followed by
the three-byte rotation provides the next multiplier bit in carry and
shifts a product bit into `r23`. The branch executes three pairs of
ordinary bits followed by a pair whose final bit subtracts the
multiplicand, accounting for the signed history high byte. This removes
seven separate multiplier shifts and adds four rotations to the low
product byte. Only the last four bits shifted into that byte survive the
Q12 mask. The final correction for negative `a` and the individual Q12
floors are preserved. The rotating multiplier byte needs no new registers.

The optimization applies to the AVR25 assembly backend with
`LPX4_AVR25_SATURATED_PRODUCTS=1`. The build still requires the real AVR25
architecture macros and `LPX4_ENABLE_ASM=1`. The original C arithmetic
remains selectable with `LPX4_ENABLE_ASM=0`; it also supplies the independent
arithmetic reference. Manufacturer headers and Flash access use the same
selection as before. This is original project assembly for the AVR GCC ABI.

## Playback measurements

The matched baseline is `84de5ce4`. At 16 MHz and 8 kHz, simavr 1.6 runs
both universal builds with the 38-cycle Timer1 IRQ, SRAM512, LPC2,
MUL16 unroll 2 and a 32-byte queue prefilled with 24 samples. AVR-GCC 7.3.0
builds both at `-Os -flto` with the same flags. The cycle metric adds the
whole IRQ to the active decoder CPU mean. Foreground queue work is checked
through playback output intervals and queue occupancy.

All 22 workloads reproduce 308,339 PWM samples bit for bit, including
against the retained native C output. Every image saves 6 Flash bytes, for
5478–5479 program bytes excluding the compressed audio. Nineteen cases
speed up and three tie. The heaviest case improves from 1760.15 to 1748.39
cycles per sample with IRQ, with its minimum queue depth rising from 8 to
16 samples. Peak stack stays at 62 bytes, and no queue underruns occur.
The nine fixed-header website builds compare byte for
byte to the baseline at their catalog gains.

The existing arithmetic and ABI probe passed 256,366 cases per backend
with interrupts active, covering all signed16 history values for selected
coefficients, both saturation hints and both history layouts. A separate
simavr probe ran 524,288 synthesis comparisons for all signed16 history
values and eight coefficients, including both signed16 endpoints. It
counted 7,973 Timer1 interrupts during the run.

Two smaller looped versions of the carry scheme saved 24 and 48 bytes
but added 11.76 and 23.52 cycles per sample on the heavy workload. They
produced 6 and 56 underruns, respectively. A direct radix-4 digit with up to
three additions per pair grew Flash and slowed both controls on which it
was screened. The selected code uses two carry rounds for a pair.

[Per-load measurements and arithmetic verification](measurements.json).

## Reproduce

From the repository root, use a fresh ignored output directory. With the
AVR toolchain and simavr installed in Ubuntu WSL, run the paired comparison:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-lpc-pairs --target tiny --baseline 84de5ce4 --wsl Ubuntu
```

Run the arithmetic probe with the AVR toolchain and Node.js:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py build/tiny-lpc-math --mul16-unroll 2 --saturated-products
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/tiny-lpc-math --exhaustive-synthesis
```
