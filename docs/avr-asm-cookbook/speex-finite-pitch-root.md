# Replace a finite fixed-point root with exact byte results

Target measured: ATmega328P / classic AVR5, GNU ABI, AVR GCC 7.3.0,
avr8js 0.21.1. Benefit measured here: isolated scalar execution time and
function/table size. Whole-decoder integration and IRQ admission are separate.
The new lookup is portable C; it adds no handwritten assembly.

NB1 pitch is a seven-bit packet field plus 17, so only 17..144 can reach the
vocoder root expression `spx_sqrt(2*(int16_t)pitch)`. The pinned Xiph fixed-point
polynomial returns twelve integers 5..16 over this complete domain. Retain those
exact 128 results as bytes in Flash, read one through the existing table-memory
abstraction, and widen the result before the unchanged pulse multiplication.
Do not replace this with a library square root: the relevant oracle is the
fixed-point polynomial with its casts and arithmetic shifts.

The useful pattern is finite composition: prove the caller's domain, evaluate
the original expression over every input, then replace computation with an
exact map. A private lookup may omit bounds checks only while the packet parser
guarantees that complete domain. It is not a general square-root API.

| Isolated O2 wrapper, including RET | Function bytes | Table bytes | Cycles min..max | Uniform 128-input mean |
| --- | ---: | ---: | ---: | ---: |
| Original polynomial, ASM enabled |368|0|257..353|322.25|
| Byte lookup, either backend |16|128|13..13|13|
| Balanced threshold tree, either backend |116|0|13..17|15.15625|
| Original polynomial, ASM disabled |244|0|558..653|622.3828125|

The lookup removes all 12 byte MUL instructions executed by the original
polynomial per call. The tree saves 28 combined bytes against the lookup but
takes more mean cycles; the lookup follows the speed-first objective. These
function/table numbers do not establish the final firmware size after inlining,
shared helper removal and LTO. Positive-gain NB1 preparation calls the root
once per frame; zero-gain frames skip it, so scalar speedup is not frame speedup.

The table uses `AVR_TABLE` / `AVR_READ_I8`, independent of arithmetic backend.
On AVR this places 128 bytes in program Flash and uses LPM without persistent
SRAM. On other targets the platform's existing memory abstraction applies;
no cross-architecture timing is inferred. `SPEEX_NB1_PITCH_ROOT_TABLE=0`
explicitly selects the original portable arithmetic even on the optimized AVR.
The direct `speex_nb1_pitch_root_c()` reference remains available as well.

Four fixtures cover ASM-enable 1/0 and lookup-enable 1/0. Each runs all 128 pitch
codes through original, lookup, threshold and selected recipes, checks a separate
BigInt polynomial, exact Flash addresses and read-only input, and checks all 512
returns for arbitrary callee-saved register patterns and zero r1. The combined
four fixtures check 2048 returns. The scalar C controls do not execute a C decoder.
No interrupts or physical board are included in this isolated screen.

```sh
python Codecs/Speex/AVR/tests/build_nb1_pitch.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_nb1_pitch.mjs Codecs/Speex/AVR/build/nb1-pitch-unit/asm-table1
node Codecs/Speex/AVR/tests/verify_nb1_pitch.mjs Codecs/Speex/AVR/build/nb1-pitch-unit/asm-table0
node Codecs/Speex/AVR/tests/verify_nb1_pitch.mjs Codecs/Speex/AVR/build/nb1-pitch-unit/c-table1
node Codecs/Speex/AVR/tests/verify_nb1_pitch.mjs Codecs/Speex/AVR/build/nb1-pitch-unit/c-table0 --record
```

The builder uses `-Os -flto -fno-ipa-icf -mcall-prologues -mrelax`, existing
fixed-point flags and O2 wrappers; disabling identical-function folding keeps
each measured entry distinct. Firmware, source copies and individual logs stay
ignored. The compact [source-bound receipt](../../Codecs/Speex/AVR/reports/nb1-pitch-unit.json)
retains the measured recipes without absolute host paths or media data.

[Private helper](../../Codecs/Speex/AVR/src/nb1_pitch.h),
[independent scalar checker](../../Codecs/Speex/AVR/tests/verify_nb1_pitch.mjs),
[pinned Xiph 1.2.1 polynomial](../../Codecs/Speex/AVR/vendor/speex-1.2.1/libspeex/math_approx.h),
[BSD license](../../Codecs/Speex/AVR/vendor/speex-1.2.1/COPYING).
The finite-domain derivation, table and threshold screen are original project work.

The caller integration was also measured on frozen AVR decoder-mailbox images,
with identical sources/options except explicit `SPEEX_NB1_PITCH_ROOT_TABLE=0/1`.
WB3.95 enabled low-rate mask 7 and NB4; the minimal-feature NB2.15 image enabled
mask 4 and disabled NB4. These numbers include the test mailbox, not a PWM player.

| Linked ASM image | Polynomial / table Flash | Flash saved | Polynomial / table mean frame cycles | Static SRAM / peak stack |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 |24,344 / 24,108 B|236 B|217,728.917 / 217,647.760|1,284 / 163 B, unchanged|
| NB2.15, minimal features |12,054 / 11,904 B|150 B|102,563.828 / 102,433.828|1,096 / 111 B, unchanged|

Each image passed 384 frames: 128 each from retained coverage, English and Russian
streams, with independent PCM and reset checks. Positive-gain frames saved 189..237
cycles in WB and 230..278 in NB. Zero-gain frames skip the root, but the linked
table images cost 63 / 4 extra cycles on those frames. The largest observed
regression is 0.020% of a 320,000-cycle frame budget; the measured mean still
improves. Whole-image compiler/link effects must be measured rather than inferred
from the scalar lookup. Interrupts were excluded from this bounded comparison;
the combined production IRQ/playback gate remains separate.

All 17 sources of the earlier 128-case scalar proof matched, and all four scalar
fixtures were rebuilt to identical binaries before reusing that proof. NB/WB
portable exports include `nb1_pitch.h` and retain explicit polynomial selection;
no complete C decoder was executed. The frozen snapshot, matched packet timing
arrays, byte-pinned tools, build/export checks and source-bound receipt are retained
in the [source-bound receipt](../../Codecs/Speex/AVR/reports/nb1-pitch-size-admission.json)
and its ignored evidence pack. The tracked `tests/run_pitch_root_size.py`
driver freezes sources and scalar references into a fresh output directory,
then builds TABLE=1/0 controls and observes the supplied WB/NB corpus excerpts.
Historical receipt checks additionally need the retained original snapshot;
reproducing against later sources creates a new measurement.
