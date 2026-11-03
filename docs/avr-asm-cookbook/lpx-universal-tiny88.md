# LPX: runtime-header playback on AVR25

Original MicroMusic work for ATtiny88 / AVR25 without MUL, GNU AVR ABI,
AVR-GCC 7.3.0, requested 16 MHz / 8 kHz, simavr 1.6. This is simulator
evidence; no physical-board or analog-output measurement is claimed.

## Keep recording parameters in the file

The default Tiny88 builder/verifier now uses the ordinary LPX v5 header:
P4/P6 and extra-pulse flags, sample count/rate, pre-emphasis and brightness
coefficients, packet geometry and bounded payload length. It does not define
`LPX4_FIXED_PRE_Q14`, `LPX4_FIXED_BRIGHT_Q14` or `LPX4_FIXED_SPEECH_FLAGS`.
Existing header validation, error handling and the portable decoder interface
remain. `--fixed-header` explicitly selects the earlier ROM specialization.

The universal profile uses the standard codec PWM transfer and unity extra
player gain. It rejects per-record compile-time gain and fixed-header defines.
No new file format is introduced. The same compiled host decoder is checked
on 60 combinations of profiles, extra-pulse flags and file-defined filter
parameters against a separately compiled standard-memory C configuration.

## Exact general arithmetic

For `0 <= c < 16384` and unsigned16 `u`, start `A=0` and process the fourteen
bits of `c` from least to most significant:

```
A = floor((A + bit[j] * u) / 2)
```

After fourteen rounds `A=floor(c*u/16384)`. Preserve the seventeenth addition
bit in carry through the two ROR instructions. For signed16 state `s`, use
its unsigned word and subtract `4*c` modulo16 if `s<0`; the resulting signed
word is exactly `floor(c*s/16384)`. The endpoint `c=16384` returns `s`.
Runtime byte shifts consume eight low coefficient bits, then six high bits;
no discarded 32-bit product or sign-extended shift is constructed. The
universal recipe uses the unrolled shared attenuation function. This is not
specialization for selected coefficient values.

For signed16 `a` and saturated synthesis history `h=+32767`:
`floor(a*h/256) = 128*a-ceil(a/256)`. For `h=-32767` it is
`-128*a+floor(a/256)`. Construct the signed24 result and retain the existing
Q12 nibble clearing and accumulator operations. A coarse hint from the latest
history high byte lives in SREG.T inside the private ASM block; it avoids
checking saturated cases at every ordinary wide product. A false hint only
misses an optimization: the general product remains exact. The private T bit
is covered by the `cc` clobber and preserved by the selected interrupt handler.
`LPX4_AVR25_SATURATED_PRODUCTS=1` enables the saturated-product and compact
Q14-clipping bundle explicitly; zero retains the original product and clipping
routes used by the published recording-specific builds.

For signed16 Q14 clipping, the high byte transformed modulo256 by `+64`
classifies `[-16384,16383]` without two full-word comparisons. Outside that
range, select `+16384` or `-16384` from the transformed sign-region bit.
`+16384` clips to itself. Every signed16 input is checked independently.

All ASM still requires a supported real architecture and explicit
`LPX4_ENABLE_ASM=1`. C and forced-generic C stay selectable on the same AVR.
Hardware memory access and decoder source selection remain independent.

## Buffer, compiler and hardware contracts

Universal builds select `-Os -flto -mcall-prologues -mrelax`, function/data
sections, garbage collection, `-finline-small-functions`, multiplication
unroll2, FIFO44/prefill33, and the existing reserved-register ASM ISR.
FIFO44 uses the same bounded non-power-of-two addressing as FIFO24, with the
queue length passed as an assembler operand. Its C ISR remains selectable.

The private player initializes OCR1A to128 before enabling interrupts and
subsequently performs no other 16-bit Timer1 access. With
`LPX25_REUSE_TIMER1_HIGH=1`, the ISR can reuse the initialized zero high-byte
latch and write only OCR1AL. This saves four Flash bytes and two IRQ cycles.
The opt-in must not be copied to code that reads/writes TCNT1, ICR1 or another
Timer1 high byte while playback is active. The manufacturer documents the
shared latch and its reuse in sections12.3/12.3.1 of the
[ATtiny48/88 datasheet, 8008H](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf).
Register addresses still come from the pinned official DFP, not this note.

## Measured admission

The [source-bound receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/universal-measurements.json)
records eight complete public P4/P6 recordings and six independent synthetic
streams: changing/clustered spectra, lag18/145, extra pulses and boundary
filter parameters including0/1/16383/16384. All fourteen have exact full PWM
against portable C, matching sample/timer counts, zero underruns, drained
queue and stopped sample timer.

| Quantity | Measured result |
| --- | ---: |
| Program Flash, including startup/tables/player, excluding one verified audio array | 5487..5488 B (about 5.36 KiB) |
| Full image including each test recording | 5958..7386 B |
| Static SRAM including FIFO44 | 447 B |
| Largest observed stack | 60 B |
| Minimum observed margin, observer's conservative SP convention | 4 B |
| Mean decode wall cycles/sample, public recordings, with IRQ playback | 1595..1722 |
| Same mean, synthetic controls | 1034..1335 |
| Maximum complete ISR including four-cycle hardware entry and RETI | 42 cycles |

Means include the initial33-sample prefill; interrupts are active for playback.
The four-byte observed margin leaves no allowance for an additional application
or ISR. This admission is bounded to the recorded standalone workloads;
universal parsing is not a proof of real-time capacity for every possible
valid spectral sequence or integration. Thirteen of fourteen measured complete images exceed
the6012-byte USB application region and require ISP; the 5958-byte image fits. The hard cap remains
8192 bytes including audio.

Before the reset compaction below, the admitted FIFO44 recipe occupied
5587..5588 program bytes. The initial unpinned FIFO24 recipe occupied5557..5558
program bytes but had
157..1014 underruns on the four original screening streams. The original admission
spent30 more program bytes and20 more static SRAM bytes to meet the measured
real-time requirement with parameters read from the file; the later reset
compaction saves 100 program bytes without changing that timing or SRAM. A pure compiler change
did save168 program bytes, but the faster general arithmetic spent that
space again. A smaller looping attenuation, one-shot control pruning and
mirrored history were measured and rejected because of timing, size or stack.

Direct AVR arithmetic/ABI checks run436207 cases on each of C, ASM and
forced-generic C, with active Timer1 IRQs and no lost interrupts. They cover
all signed16 clipping inputs, every coefficient0..16384 on boundary states,
full signed16 states for four dynamic coefficients, saturated products,
floor/rounding boundaries, r1, callee-save registers and stack balance.

Reproduce from the repository root (add `--wsl Ubuntu` to the player command
on Windows; run the primitive build with the existing Linux AVR toolchain):

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_universal.py build/tiny88-universal
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py build/tiny88-universal-math --mul16-unroll 2 --saturated-products
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/tiny88-universal-math --exhaustive-dynamic
```

## Compact shared state reset (2026-11-03)

The private transient fields from `blockStep_` through the end of `cur_`
contain only zero-initialized integral values and arrays. Clear that span
with one `memset`, using `offsetof` and the final member's size; this includes
any interior padding. Input pointers, bounded-source state, public metadata,
remaining count and optional callback ownership stay outside it. LPC anchors
and polynomial workspace are written before use and do not need clearing.
Keep one non-inlined reset shared by construction and `begin()` even with LTO.
No class layout, stream header, error precedence or arithmetic backend changes.

Against revision `85d354a9`, with the identical compiler/options/workloads:

| Quantity | Before | After |
| --- | ---: | ---: |
| Reset function | 122 B | 22 B |
| Program excluding verified audio | 5587..5588 B | 5487..5488 B |
| Static SRAM / largest observed stack | 447 / 60 B | 447 / 60 B |
| Complete ISR | 42 cycles | 42 cycles |

All fourteen full-playback PWM streams and measured decode means/maxima,
IRQ-active means, queue minima, stack and output intervals are identical.
The source-bound receipt records each before/after pair. This saves 100 B
(0.09765625 KiB, about 1.79%) without doing less work on the audio path.
Reset inlining saved 84 B; sharing its loop saves another 16 B. A simpler flags
mask generated identical code and was not retained.

The frozen parser trace still passes 1,838,989 cases in each of four builds.
A separate 10,400-case before/after portable C check covers ROM/callback
switching, failed begins, truncated/malformed headers, both cursor modes,
standard/compact parsers and PCM/PWM outputs. Existing reset/copy and dynamic
header tests also pass. The arithmetic files are unchanged, so the independent
C/ASM/generic primitive receipt above remains applicable.

Rebuilt public fixed-header Tiny88 demos save 98 B each (5320..7034 B including
audio), retain all existing PWM samples, and have zero underruns. Their
recording-specific builds remain distinct from the universal measurements.
