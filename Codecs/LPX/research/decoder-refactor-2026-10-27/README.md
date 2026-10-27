# LPX decoder reset/LPC refactoring, 2026-10-27

The active Hybrid decoder shares its synthesis reset between construction and
`begin()`, removes unreachable LPC interpolation code, and calls the existing
LSF interpolation directly. On all eight fixed speech streams, the established
small-code AVR recipe saves **160 bytes** in the common build and **156 bytes**
in compact-only. Useful PWM and measured decode cycle totals are identical.

## Change and boundaries

- `resetSynthesis()` owns filter, spectrum, LPC-anchor and excitation-history
  initialization, including diagnostic counters. Input pointers, sample metadata,
  parsing state and errors stay with the constructor/`begin()` lifecycle.
  A failed `begin()` retains its previous public counter/error behavior.
- The old alternative interpolation branch was excluded by the unconditional
  `LPX3_FAST_LPC_INTERP` definition. It referred to the removed `coeffBits_`
  field. Removing it is dead-source cleanup; that branch occupied no firmware.
- The private `interpolate()` forwarding wrapper and unused local `coeffBits`
  constant are removed. Readers, container parsing, excitation, LPC conversion,
  and sample synthesis have explicit responsibility markers in the same
  translation unit. Existing explicit build commands and include-based probes
  continue to work.

Public interfaces, field order and object layout, supported formats and feature
defaults are unchanged. The independent C arithmetic fallback, explicit ASM
opt-in, hardware Flash access, and retained LPX3 reference/oracle are unchanged.
No encoder search, recompression, new assembly or vendor definitions are involved.

## Measured scope

Baseline: `7c6edee7e3b96a70ca11dfabb8fe43c76cd095e3`, copied to an immutable
local source snapshot before editing. Target: ATmega328P / enhanced AVR5 with
MUL, GNU ABI, AVR-GCC 7.3.0, simavr 1.6, 16 MHz CPU / 8 kHz PWM, queue512,
prefill384, LPC segments2.

The small-code recipe is unchanged:
`-Os -flto -mcall-prologues -mrelax`,
`LPX4_AVR_DOT_UNROLL=1`, `LPX4_FUNCTION_TUNING=0`, explicit ASM enabled.
Both measured builds enable speech v4/v5 and v3 feature mask24; compact-only
also sets `LPX4_COMPACT_ONLY=1`. Exact flags, source/toolchain hashes,
per-image results and simulator identity are in [measurements.json](measurements.json).

**Program Flash = .text + .data minus exact embedded compressed-stream bytes.**
The existing benchmark verifies the array's size, bytes, uniqueness and Flash
placement before subtraction. Startup, runtime, codec tables and the unchanged
profiling/playback harness remain included. This is not an isolated library size.

| Build / workload | Before, program bytes | After, program bytes | Saving | Static SRAM |
| --- | ---: | ---: | ---: | ---: |
| Common, small-code recipe, eight streams | 7889-8030 | 7729-7870 | 160 per stream | 1105, unchanged |
| Compact-only, same eight streams | 5909-5910 | 5753-5754 | 156 per stream | 1085, unchanged |
| Common, default recipe, case-03-4 only | 9172 | 9084 | 88 | 1105, unchanged |
| Compact-only, default recipe, case-03-4 only | 6880 | 6796 | 84 | 1085, unchanged |

Default-recipe rows are size screens, not new timing admissions. Layout and LTO
can change sizes for other streams/toolchains; the observed savings are scoped
to these images.

## Validation

- The same 46 focused host tests passed before and after, covering readers,
  formats, tails/errors, restart/copy behavior, all LPC anchor counts, reference
  state configurations, signed/PWM outputs and portable arithmetic.
- All 111 stored legacy golden points, representing 91 unique streams, retain
  exact PCM16 and PWM hashes.
- Each source revision completed 28 full firmware simulations: 16 four-second
  images plus 12 continuous 64k-sample controls across the two layouts. Every
  useful PWM byte matches saved WAV references checked against the independent
  integer model. Normal ASM and +100-cycle IRQ controls have zero underruns.
- Per-image decode wall-cycle totals, including IRQ/instrumentation, are
  identical before/after, including controls. Mean over the eight main images:
  common 846.640582 cycles/sample; compact-only 785.018543.
- C fallback remains output-exact and retains its prior deadline misses;
  real-time 8 kHz is not claimed for it.
- Both layouts passed 605670 mutation/reset cases each under Linux GCC
  ASan+UBSan, with exact resets and no sample-cap exhaustion.
- Static SRAM and observed after-ready stack margin are unchanged: 819 bytes
  common, 858 bytes compact-only. No physical board or startup/worst-case
  stack proof is claimed.

## Reproduction

Use the unchanged active tools and locally retained frozen inputs; generated
audio headers, binaries, caches and raw logs belong in ignored `build/`.
The established local Python dependencies, native compiler adapter, AVR-GCC
and WSL/simavr setup are described by the earlier
[speech Flash study](../speech-flash-2026-10-26/README.md).

Run the 21 host test modules listed in `measurements.json`.
Run [the legacy golden verifier](../q0-decoder-size-speed-2026-10-26/reproduce.py)
with `--native-only --root <local-golden-cache-root>`.
For each source revision, run
`tools/benchmark_speech_flash.py screen` with
`--candidates unroll1-tune0-lto-call-relax` and
`tools/benchmark_speech_flash.py verify` with
`--candidate unroll1-tune0-lto-call-relax`, supplying the same
`--source`, `--study`, `--avr-bin`, `--runner`, `--lib`, and `--wsl Ubuntu`
as appropriate. Repeat each with `--compact-only`.
Use `tests/verify_fuzz.py --wsl Ubuntu --v3-features 124 --speech --speech-compact`
and repeat with `--compact-only`. No arithmetic backend or compiler recipe
changed, so an additional AVR arithmetic-only search was unnecessary.

Only anonymous measurements, hashes and source changes are retained here.
