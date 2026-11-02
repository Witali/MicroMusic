# LPX Tiny88: tighten RAM and complete-image Flash budgets

Original MicroMusic techniques for **ATtiny88 / AVR25 without MUL**, GNU AVR
ABI, AVR-GCC 7.3.0 and GNU assembler. The complete player uses `-Os -flto
-mcall-prologues -mrelax -fno-inline-small-functions -fno-jump-tables`,
function/data sections and linker garbage collection, requested 16 MHz / 8 kHz.
Device registers come from the pinned official
[Microchip ATtiny_DFP 3.4.278](../../ATtiny88/Music/universal/vendor/README.md).
These are simulator measurements, not physical-board or analog-output results.

## Remove storage only after pinning and checking ROM parameters

The ROM recipe already defines `LPX4_FIXED_PRE_Q14`,
`LPX4_FIXED_BRIGHT_Q14` and `LPX4_FIXED_SPEECH_FLAGS` from the unchanged input
header. `begin()` rejects a mismatched header. In the SRAM512 layout, omit only
the corresponding private fields: two 16-bit constants and one flag byte.
Arithmetic and format accessors use the same fixed values. This saves **five
bytes of decoder state: 398 -> 393**. The completely unpinned SRAM512 library
layout remains 398 bytes; the standard memory profile is unaffected.

Define the same memory profile and fixed-header options in every translation
unit because they determine object layout. Retain dynamic-header tests,
partial fixed-header combinations, reset/copy behavior and the parser's
mismatch rejection. Constant values alone are insufficient proof that a field
can disappear: every read and write must use the same specialization.
The [original 96-byte dead-history workspace proof](lpx-sram512.md) is separate
and remains necessary.

## A 24-byte FIFO needs different addressing and real ELF inspection

FIFO32 remains the default. Its 32-byte alignment permits `base | tail` and
mask wrapping. The optional FIFO24 has 23 usable slots and prefill 18. Use
byte alignment, add the symbol address to the byte index with carry, and wrap
at 24 with a compare/branch. In the ISR the low address byte can be converted
back to the index after the load because the offset is below 24; preserve the
full address carry during the load. The C ISR uses the same bounded ring
semantics and is independently selectable.

An initial `aligned(32)` declaration for the 24-byte array produced a 32-byte
ELF section in this recipe: shrinking the C array alone saved no total RAM.
The selected byte-aligned section really occupies 24 bytes. Inspect the
linked section and symbol sizes, rather than inferring total allocation from
`sizeof`. Combined with fixed-state removal, static player SRAM falls
**435 -> 422 bytes**; retaining FIFO32 gives 430 bytes.

The audited ASM ISR still reserves r2/r3 with whole-program
`-ffixed-r2 -ffixed-r3`, preserves Z and leaves r1 untouched. FIFO24 costs
**44 cycles**, versus 40 for FIFO32, including four hardware-entry cycles and
completed RETI: four extra cycles per 2000-cycle sample period is **0.2% CPU**.
The measured FIFO24 C ISR costs 65 cycles. Do not reuse the reserved registers
in an unaudited library or add an ISR without rechecking the complete image.

## Group software-product rounds while preserving carry

The [production multiply header](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4MultiplyAvr.h)
accepts `LPX4_AVR25_MUL16_UNROLL` values **1, 2, 4, 8 or 16**, with **16 retained as
the default**. Smaller factors loop over groups of the original carry-rotation
body. `LDI` initializes the group counter without changing carry; `DEC` and
`BRNE` preserve the final `ROR` carry needed by the next multiplier bit. The
same two modulo-2^32 signed corrections follow all sixteen rounds, including
the signed-minimum cases. The extra counter needs an early-clobber high
register constraint; the 32-bit product must not overlap either original
operand. This changes code size and execution cost, not the arithmetic.

Both this arithmetic and the short ISR require the real supported architecture
plus their separate explicit enables: `LPX4_ENABLE_ASM=1` and
`LPX25_ENABLE_ASM_ISR=1`. Portable C remains the default, including on AVR25;
`LPX4_ARCH=LPX4_ARCH_GENERIC` forces it on the same actual target. Hardware
Flash access is independent of arithmetic selection. Compare C, ASM and
forced-generic against the same independent integer/reference output.

The selected public recipe uses **factor 2**, explicitly requested through
`--mul16-unroll 2`; the library/builder default remains 16. In two isolated
FIFO24 comparisons before the P4 table change, complete P4/P6 images fall
**6448 -> 6258 / 6090 -> 5900 bytes**, saving 190 bytes each. IRQ-active decode
means change **1518.949 -> 1525.252 / 1619.409 -> 1625.961 cycles/sample**.
The independent primitive harness also shrinks 3528 -> 3338 bytes. Factor 1
saves only 14 more bytes and costs about another 6.5 cycles/sample on the P6
comparison, so it
was not selected for the public recipe. These isolated numbers do not include
the later P4 table saving.

## Store only reachable fixed-P4 cosine nodes

In compact-only SRAM512 ROM builds with fixed P4 flags and segments 1/2, the
existing half-grid node index is always even. Reflection `128-index`
preserves parity. Retain the exact 33-word subset of the existing 65-word
table and use `index>>1` after reflection: **64 fewer table bytes**, without
rounding or changed coefficients. P6, unpinned headers and four-segment builds
retain their prior table/helper. This specialization is portable C and is
shared by the C and ASM arithmetic builds. Keep the independent full oracle.
The [grid-cosine entry](lpx-v5-grid-cosine.md) records coordinates and guards;
complete-image size also includes the changed lookup code and linker layout.

## Measure the complete player and distinguish loading limits

The [source-bound anonymous receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/budget-measurements.json)
records before/after runs and the FIFO24 matrix. Nine complete public
P4/P6/S15 phrase/profile combinations are decoded twice, with exact independent
PWM, active Timer0/Timer1,
zero underruns, empty final queue and stopped sample timer. The memory change
raises the minimum observed stack margin **10 -> 23 bytes**; peak observed
stack is 66 bytes. This is the observer's conservative SP convention, not a
proof of stack headroom for arbitrary streams or startup/application code.
Dense P6 cases, changing/clustered spectra, lag boundaries, reset chains and
tails are separate matrix gates. C arithmetic and FIFO16 retain their
rejection controls; an exact decoded output does not establish real-time fit.

Matched before/after builds use the same full phrases and repeat geometry.
The selected FIFO24/unroll2 ASM recipe saves **202..272 program bytes**, with
at most **0.510%** increase in mean IRQ-active decode cost, exact PWM and zero
underruns on all nine combinations. The final matrix has 18 cases: 16 admitted
and two intended timing rejections; explicit smaller-Flash-cap rejection is
checked separately. All five unroll factors pass 26,262 arithmetic/ABI cases
per C/ASM/forced-generic backend, **393,930 backend-case runs** with live IRQs.
The exact P4-table tests cover 1808 nodes, 48 scenarios and 120 complete
PCM/PWM comparisons. The release target uses existing AVR25 ASM arithmetic and
the ASM ISR; C remains explicitly selectable on the real target.

The selected FIFO24/unroll2 one-shot release separately checks all nine
complete combinations: 141,708 PWM samples, identical to the independent C
reference and the existing public WAV. Complete Flash is **5418..7132 bytes**,
including the original audio; program cost after subtracting the verified
single audio array is 4947..5233 bytes. All use 422 static SRAM bytes, observed
stack at most 66 bytes and margin at least 23 bytes. Six images fit the
standard USB region, including the complete 19,200-sample P4 image at exactly
6012 bytes; the remaining three require ISP. This one-shot release check is
separate from matched repeated-playback optimization measurements.

The hard limit is **8192 bytes for the complete image**, including compressed
audio. Treat roughly 6 KiB as a bootloader warning: the standard MH-ET LIVE USB
application region is actually **6012 bytes**. Larger images require ISP
loading; pass `--flash-limit 6012` when USB fit is mandatory. The former
6656-byte gate remains only in historical receipts. Speex is excluded from
this Tiny88 profile.

Use the [current player guide](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/README.md)
for reproduction and the physical limits. No audio, source level, sample
count or codec parameters are changed to obtain these savings. The bounded
simavr 1.6 adapter models the two timers and explicitly charges IRQ entry and
RETI completion. It is not a full board model, and requested 16 MHz does not
extend the device manufacturer's ordinary speed rating.

The [original integration entry](lpx-avr25.md) retains algorithm/ABI/timing
references and earlier receipts. These changes reuse original project code;
no vendor assembly listing was copied. Manufacturer licensing and provenance
remain with the unchanged vendor definitions.
