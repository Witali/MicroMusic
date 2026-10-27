# Further LPX program-Flash reduction, 2026-10-27

Relative to decoder commit `5dea80be`, the same fixed speech images save another
**504-550 program bytes** in the common build and **390 bytes** in compact-only.
Compressed data, PCM16/PWM values, formats, feature defaults and compiler recipes
are unchanged. Average measured decode wall time increases **3.09% / 2.51%**;
all measured ASM normal and +100-cycle IRQ controls still have zero underruns.

## Source changes

- `resetState()` shares all identical parser/synthesis scalar initialization
  between construction and `begin()`. Named arrays use their own `sizeof`
  with `memset`; no cross-field offset ranges or field-layout changes are used.
  Callers retain input, public stream metadata and remaining-count setup.
- V4 fixed-packet byte geometry uses unsigned16 arithmetic. Accepted counts are
  at most 64000, so count+319 and the maximum packet byte length fit. The existing
  full-width guard still rejects larger counts. V5 payload-length checks remain
  wide because an untrusted uint16 payload plus 22 may overflow uint16.
- Compact Rice deltas use their proven signed8 range, -64..63.
- LSF-to-LPC conversion processes ten coefficients in one loop. Independent P/Q
  polynomials retain the same degrees, first factors, contribution order and
  saturation. Adjacent cosine nodes share one reflection and two Flash reads,
  preserving negative floor rounding and endpoint bounds.
- `readOne()` delegates to `readBits(1)`, sharing cache/refill and diagnostic
  counting under the existing zero-unused-cache-bits invariant.
- The pitch predictor no longer forces inlining; the compiler can share it.
  [GCC 7.3 optimization documentation](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Optimize-Options.html)
  describes its size/inlining heuristics. No new compiler flag is required.

Hardware memory access and `Lpx4Math.h` are unchanged, including portable C,
explicit ASM opt-in, architecture checks and optional reference controls.
No new assembly, vendor files, recompression or encoder search is involved.

## Measurements and tradeoff

ATmega328P / enhanced AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0, simavr 1.6,
16 MHz CPU / 8 kHz PWM, queue 512 / prefill 384, LPC segments 2.
The established recipe remains `-Os -flto -mcall-prologues -mrelax`,
unroll 1 / tuning 0, explicit ASM; the common measurement enables v3 mask 24 and
speech v4/v5. Compact-only additionally sets `LPX4_COMPACT_ONLY=1`.

Program Flash means **.text + .data minus exact embedded compressed-stream
bytes**, after the existing benchmark proves bytes, size, uniqueness and Flash
placement. Startup/runtime, codec tables and the unchanged harness are included.

| Build / workload | Before, program B | After, program B | Saving | Static SRAM B |
| --- | ---: | ---: | ---: | ---: |
| Common, eight fixed speech streams | 7729-7870 | 7225-7320 | 504-550 | 1105, unchanged |
| Compact-only, same streams | 5753-5754 | 5363-5364 | 390 | 1085, unchanged |
| Common, default recipe, case-03-4 only | 9084 | 8750 | 334 | 1105, unchanged |
| Compact-only, default recipe, case-03-4 only | 6796 | 6456 | 340 | 1085, unchanged |

On the same eight inputs, mean decode wall cycles/sample including active IRQ
and instrumentation change from 846.640582 to 872.820309 (common) and from 785.018543
to 804.737145 (compact-only). This is a Flash/time tradeoff, not a speedup.
Observed after-ready stack margin improves 819 to 845 B and 858 to 882 B.
C fallback remains output-exact but still misses the 8 kHz deadline.

Raw source/toolchain hashes, per-image data, baseline artifact integrity checks,
and bounded screens are retained in [measurements.json](measurements.json).
The baseline reuses the complete verified images from the
[preceding refactoring study](../decoder-refactor-2026-10-27/README.md).
Each revision's continuous controls select its own heaviest source per profile;
they are admission checks, not necessarily identical before/after inputs.
Timing-growth percentages use only the identical eight fixed inputs.

## Validation and reproduction

- 46 existing focused decoder tests passed. The updated table test exhausts
  all 4096 inputs through the actual production cosine helper and the retained
  independent full table.
- An additional persistent
  [anchor regression](../../01_ACTIVE_Q0_CODEC/tests/anchor_coefficients.cpp)
  checks 34816 conversions (348160 output coefficients) against the independently
  frozen baseline digest. Its canonical little-endian output was also rebuilt
  against the immutable old source.
- Exact host PCM16/PWM across 764 stream/configuration combinations covers 91
  frozen legacy streams, eight frozen speech inputs, boundary fixtures,
  LPC segments 1/2/4, reference state configurations and compact-only.
- All 111 legacy golden points / 91 unique streams keep exact PCM16/PWM hashes.
- 28 new complete AVR images passed saved-WAV/model PWM checks: 16 four-second
  images plus 12 continuous 64k-sample controls across both layouts. Normal ASM
  and +100-cycle IRQ controls have no underruns.
- Both layouts passed 605670 mutation/reset cases under Linux GCC ASan+UBSan,
  with exact resets and no sample-cap exhaustion. Two independent code reviews
  found no actionable issues.

Run the modules listed in the measurement record plus the new native-anchor
test. Reuse `tools/benchmark_speech_flash.py screen/verify` with the unchanged
`unroll1-tune0-lto-call-relax` candidate and local frozen study, once per layout.
Run `tests/verify_fuzz.py --wsl Ubuntu --v3-features 124 --speech --speech-compact`
and repeat with `--compact-only`. Local dependencies and simulator setup follow
the [earlier Flash study](../speech-flash-2026-10-26/README.md).
The selected sources remain one translation unit, so build discovery/cache
inventories do not need new implementation dependencies.

## Rejected or unadmitted alternatives

Cross-field offset-range clearing saved more in a screen but couples reset
semantics to future field layout; the selected code clears named fields/arrays.
Linear LPC history grew code. Forced frame outlining grew the common build;
forced code/Huffman outlining did not improve both layouts. Pointer polynomial
walks lost their standalone saving when combined with the selected loop.
Disabling fast paths produced smaller size-only candidates but was not selected;
existing controls/defaults remain intact. Screen savings are not additive and
do not establish timing support.

These are simulator measurements for the specified images and settings.
No physical board, startup/worst-case stack proof, other ISA/toolchain, or
universal minimum-size claim is implied. No audio, firmware binaries, source
recording paths or personal metadata are retained in this study.
