# Exact polynomial simplification, 2026-10-28

Baseline `3f717df5`, ATmega328P / enhanced AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0,
16 MHz / 8 kHz. The fixed size recipe remains `-Os -flto -mcall-prologues -mrelax`,
unroll 1 / tuning 0, compact-only, explicit ASM, queue 512 / prefill 384 and LPC
segments 2. Source/backend selection and hardware Flash access are unchanged;
no assembly or vendor definitions were added.

## Selected: replace the trailing-unit multiplication

`convertLsfAt` initializes the trailing P/Q coefficients to +4096/-4096.
Every `polyFactor` first copies the trailing coefficient into the next trailing
slot. Therefore `p[n-1]` is always one of those two units at the next call.
Its original `polyMulQ12` fast path gives exactly +c or -c, without fractional
rounding, including every signed16 c. Replace that one general product with a
signed32 conditional negation. All other independently rounded products, wide
guards, final truncation/clamps and format behavior remain intact. Eight general
products per conversion are eliminated; this is an algorithm simplification,
not a new approximate spectrum.

On eight fixed complete linked recordings from the previous automatic selection,
full Flash is unchanged on six images and 2 B smaller on the two five-reset images.
The exact stream arrays, shared program, reset dispatcher, lookup tables, startup
and profiling harness are included. Static SRAM remains 1085 B single-reset /
1086 B five-reset. These placement-dependent results do not establish a universal
minimum library footprint.

Two 64000-sample real recordings, profiles 4/6, each with normal and extra 100-cycle
IRQ loads, were simulated before/after: all eight full PWM outputs equal the
independent model, zero underruns and decoder errors. IRQ-inclusive decode totals
improve 2.35%/2.49% normal and 2.62%/2.76% extra IRQ. After-ready observed stack
margin improves 887->889 B. Those durations cover every useful sample in these
single-reset images; they are not startup/worst-case or physical-board evidence.

Eighteen focused tests cover invalid prefixes/payload/trailing bits, partial
tails, common/compact layouts, state copy/restart and original reference flags.
An additional ordered-spectrum test also passes. The actual compiled helper
matches an independent 64-bit implementation of the old recurrence on 564288
factor cases, including every signed16 coefficient with both units and random
ordinary/split-floor products. All five measured variants match the frozen 34816
conversion digest and 69632 additional ordered/extreme conversions in both native
layouts. C remains explicitly selectable on AVR; these native tests exercise C,
while the eight full IRQ images exercise the existing explicit AVR ASM backend.
No new real-time admission is claimed for the slower C arithmetic path.

## Rejected: reciprocal P folding

P remains exactly palindromic because its mirrored updates consume identical
rounded middle products. Q's antisymmetry does not survive independent negative
floors, so every experiment preserves its full recurrence. Updating only P's
lower half removes 14 of 24 P products. Three source-only experimental patches
are retained relative to the selected unit source hashes in `measurements.json`:

| Variant | Full Flash change per image | Static SRAM change | Outcome |
|---|---:|---:|---|
| Paired outputs,6-word P | +152..160 B | -24 B | Rejected for Flash growth |
| One indexed output loop,6-word P | +70..72 B | -24 B | Rejected for Flash growth |
| Restore upper P then old output loop | +88..90 B | 0 B | Rejected for Flash growth |

These are linked-image and compiled coefficient results. No active-IRQ admission,
full lifecycle test suite or timing benefit is claimed for the rejected variants.
Their reduced multiplication count alone does not justify extra firmware Flash
under this task's priority. The production source retains the full P/Q arrays.

## Evidence and reproduction

[Measurements](measurements.json) contain anonymous image costs, exact source
hashes, fixed compiler options, retained coefficient digests and scoped timing
counters. Audio, original recording names/paths and firmware binaries stay local.
Run `tests/test_polynomial_unit.py` and `tests/test_coefficient_trace_exact.py`
with the project's Python/runtime and native compiler. Repeat complete image
measurements with `tools/measure_speech_firmware.py`, passing the same immutable
stream list and reset geometry with baseline/candidate `source` directories.
Use `simulate(...,irq=0)` and `irq=100` with the retained simavr runner to repeat
PWM/IRQ validation. The real recordings are private prerequisites; deterministic
coefficient tests do not require them.
