# Exact ROM-selected LPX output gain

Applicable CPUs: ATtiny88 / AVR25 without MUL and ATmega328P / AVR5 with
MULSU, GNU AVR ABI, AVR-GCC 7.3.0, 16 MHz. The dedicated universal v9 player
uses explicit `LPX4_ENABLE_ASM=1`; the same target can select the portable C
formula with that define set to zero. Hardware Flash access remains outside
the arithmetic choice. These are original project techniques.

The recording-independent transfer function is
`sat_u8(((sample * gain + 64) >> 7) + 128 - gain)`, for sample 0..255 and
ROM-selected gain 128..255. The gain byte belongs to the player container;
the LPX payload and its length do not change.

On AVR25, let `d = gain - 128`. The equivalent result is
`sat_u8(sample + round(sample*d/128) - d)`. Seven shift/add rounds form
`2*sample*d`; the final carry rounds the product. The correction fits signed
eight bits. Its sign equals the last ADD carry exactly when the sum is in
0..255, so the mismatch selects the appropriate saturation rail.

On AVR5, MULSU forms `P = int8(sample ^ 128)*gain`. Add 16448 modulo 65536.
An unsigned result below 32768 gives the valid duty after shifting seven
bits. Otherwise the shifted high byte distinguishes the upper and lower
overflow regions. CPI/SBC selects 255 or zero without retaining the original
sample sign. Clear r1 immediately after copying the product, including when
the multiply is interrupted.

Both implementations live in the shared player's `playbackGain`, beside
the selectable C formula. Do not apply the bounded identities to arbitrary
gain values or to another signed rounding rule.

## Measured full playback, 2026-11-17

The actual ROM-gain player uses `-Os -flto -mcall-prologues -mrelax`, SRAM512
profile, two LPC segments, FIFO32 / prefill24, reserved-register ASM ISR.
Against commit `ead0bdcb`, all 22 inputs on each CPU reproduce 308,339 PWM
samples exactly, with zero underruns. Static SRAM, peak stack and IRQ cost
are unchanged.

| CPU | Program excluding audio | Saving | Complete producer work per sample |
| --- | ---: | ---: | ---: |
| ATmega328P | 3090..3091 B | 26 B | 10 cycles less, mean and maximum |
| ATtiny88 | 3631..3632 B | 6 B | 8..9 cycles less, mean and maximum |

The external observer also counts the gain and successful queue publication.
It detects the ELF-resolved foreground head read and changed head store,
excluding full-queue retries. It subtracts complete IRQ intervals and a
partial active IRQ if needed. No instructions or counters are inserted into
the AVR image. Same-ELF replays of all 44 predecessor images retained every
old timing field and PWM byte before comparing the optimized firmware.

[Paired source-bound measurements](../../Codecs/LPX/research/avr-player-3k-2026-11-17/gain-measurements.json)
are simavr 1.6 results; no physical-board measurement is implied.

The retained `tests/verify_pwm_gain.py` extracts this actual function and
checks all 32768 input/gain pairs for each target and each explicit C/ASM
backend, with live interrupts and canaries for every callee-saved register,
Y and r1. [Exhaustive receipt](../../Codecs/LPX/research/avr-player-3k-2026-11-17/gain-exhaustive.json).
Run it from a Linux checkout with AVR-GCC and simavr development libraries;
all generated files go below ignored `build/`.

## Share the bounded Rice prefix accumulator

The v9 ROM layout limits Rice `k` to 0, 1 or 2. Accumulate `high << k` as
zero prefix bits arrive, then append the residue on the terminating one.
The eighth zero still selects the escape. Use `k+k+(k==0)` for the step and
derive `6+(flags&2)-k` only on escape, avoiding a live width through the loop.
The AVR5 reader can share the already measured AVR25 logic; explicit C and
legacy paths remain selectable. This saves another 10 B on Nano and changes
no Tiny binary. All 22 inputs per CPU retain exact PWM, IRQ timing, SRAM and
stack; complete producer mean/peak never increase. The private reader probe
also covered 28,800 traces per predecessor/successor and C/ASM combination,
including cache offsets, short ROM bounds and pre-existing errors. The
pre-existing private cache/cursor difference between C and ASM after an
already-set error is retained, rather than asserted equivalent.

The universal AVR5 24-bit polynomial path can also omit cosine node zero.
Parsed one-based spectral bins produce nodes 1..127; reflection reads only
1..64. Move the zero-valued end cursor from table index 64 to 63, preserving
all LPM instructions and arithmetic. Keep the 65-entry table for selectable
C, legacy and other geometries. This saves 2 B on Nano, with identical full
producer timing across all 22 cases and byte-identical Tiny images.
