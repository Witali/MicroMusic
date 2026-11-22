# WebAssembly optimization cookbook

## Exact pruning and duplicate elimination in LPX V9 search

Measured scalar C++ implementation for `wasm32-unknown-unknown`, exported C ABI,
32-bit linear memory and double-precision loss. Emscripten SDK 6.0.12's Clang 24
with `-O3`, freestanding/no host imports; no SIMD, threads or handwritten assembly.
The techniques reduce search runtime. They do not reduce working memory or
change the shared decoder, firmware arithmetic, or real-time IRQ support.

The implementation is original project code in
[encoder.cpp](../../web-player/lpx/native/encoder.cpp). It optimizes the existing
speech_v4 closed-loop search; it does not adapt external assembly.

### Stop candidates that cannot win

Accumulate squared PCM error in the original order. Each term is nonnegative,
and a whole 160-sample block has integer error at most `160 * 65535^2 < 2^40`,
exactly representable in a double. Once `loss >= incumbent`, later samples cannot
make that candidate win the existing strict `<` comparison. Use the current
20-sample pulse incumbent inside a trial and the block incumbent between
subframes. Discard every aborted trial's partial filter/ring state.

Replay each winning pulse fully to produce the next subframe state. Replay the
winning block fully to commit pulses, expected PCM and state. Both replays use
an infinite bound. Do not reorder candidates, change the tie comparison, or
reuse a partial state as a winner. Analysis, rounding and packing are unchanged.

### Eliminate equivalent candidates while retaining their first wire code

Several allowed scale codes map to the same `steps[scale * 8]`. At the same
initial state, lag and gain, they run identical arithmetic and select identical
pulses/history. Skip a scale only when an earlier *admitted* scale has the same
step. Retain the first code because its wire representation wins equal errors.
The incumbent only decreases, so an earlier bounded rejection remains a loser
when an equivalent candidate appears later. When estimated pitch gain is 14,
the later fixed-gain-14 candidate is also redundant.

Do not equate zero-step candidates with different gains: they can store different
ring histories even when the current audible output is zero. Do not replace
equal output with a different encoded scale/pulse representation.

### Reuse the exact state before a pulse

For each subframe/scale/gain, run a zero-impulse trial once and cache the state
and cumulative loss immediately before each of its 20 sample positions. A
candidate at position `pos` has the same prefix, so clone that snapshot and
continue the unchanged synthesis/error loop at `pos`. If the cached prefix
already reaches the incumbent loss, discard the candidate before copying it.
Winner replay still starts from the original state and writes every PCM sample.

Snapshots include all ten LPC history values, de-emphasis state and the complete
256-entry excitation ring. In particular, lags 18/19 can read excitation already
generated in the same subframe; cloning only filter history would be incorrect.
Build a fresh cache for every subframe/scale/gain and preserve candidate order.
The loss is the same exact integer-valued double prefix sum; no sum is reordered.

This scalar wasm32 implementation adds `20 * (267 * 4 + 8) = 21520` bytes of
static cache per encoder instance, plus alignment. Keeping the cache outside the
32 KiB stack avoids a large stack frame. The encoder already owns mutable state
per WASM instance; instances do not share this cache. Limits and workspace
buffers are unchanged. `LPX_ENCODER_REUSE_PREFIX=0` selects the original C trial
on this architecture; no assembly, SIMD or browser isolation changes are needed.

The [prefix experiment](../../research/web-encoder-prefix-search-2026-11-22/README.md)
records additional speed relative to the already pruned/deduplicated encoder,
not relative to the original exhaustive version. A dedicated compiled harness
checks 918000 state/loss/bound cases, including lags 18/19, ring wrap, all pulse
positions/amplitudes, saturation and exact ties. Full-stream differential tests
and the shared-C decode/model validation remain enabled.

### Commit strictly silent blocks without searching

Keep the original guard: zero residual power, zero de-emphasis state and all
ten LPC history values zero. With scale zero and gain zero, every pulse
candidate synthesizes zero, so strict ties always select position zero and
amplitude -8. Write those eight pulses and 160 expected zero samples directly.
Overwrite only the block's 160 ring entries, preserving the other 96 entries;
do not erase excitation history. The guard and parameter packing are unchanged.
`LPX_ENCODER_FAST_SILENCE=0` selects the original search path.

The direct harness compares the complete resulting state/PCM/pulses at all eight
ring alignments, both profiles, and zero/tiny/full-scale sources. Stream tests
also cover leading silence, decay into a pause and resumed excitation. The
shortcut alone saves only 4-8% on the recorded silence workload after items 1-3;
analysis dominates its remaining runtime.

### Cache the exact fixed-grid trigonometric terms

The 641 LSF grid points (including the original `1e-6` starting point) and the
256-sample Hamming window are constant across frames/rates/profiles. Initialize
the original double `sin`/`cos` expressions once per WASM instance. Cache all
`2 * 641 * 11` terms and retain the original scalar multiply/add order for root
values. Keep bisection between grid points on the original trigonometric code;
use no recurrence, approximation or root interpolation.

The table consumes 112816 bytes plus alignment/ready state, generated at runtime
rather than embedded as a large download. The direct harness checks 20768
Hamming values, grid terms and root sums bit for bit, including cancellation.
`LPX_ENCODER_CACHE_ANALYSIS=0` selects per-call window preparation and direct
grid evaluation. The [analysis/cache experiment](../../research/web-encoder-analysis-cache-2026-11-22/README.md)
records first-encode and warm measurements, all output hashes and full checks.
The first-encode measurements matter because the browser creates a new Worker
for each conversion. This is an offline Web/PC optimization; existing firmware
timing support is not changed.

### Measured SIMD and compact-prefix alternatives

On the same scalar source, `-msimd128` gave 0.98-1.02x whole-encode ratios and
increased WASM from 43922 to 45670 bytes. A compact prefix cache reduced its
21520 bytes to 1120 bytes but slowed non-silent cases by approximately 23-45%.
Both passed the same direct state/math harnesses and 87-case stream suite. They
are reproducible experiments, not selected production backends. Keep the
simpler scalar/full-prefix implementation for these measured workloads; no
general claim about explicit SIMD kernels or other CPUs follows from this test.

### Fallback and evidence

`LPX_ENCODER_ENABLE_PRUNING=0`, `LPX_ENCODER_DEDUP_CANDIDATES=0`,
`LPX_ENCODER_REUSE_PREFIX=0`, `LPX_ENCODER_FAST_SILENCE=0` and
`LPX_ENCODER_CACHE_ANALYSIS=0` independently disable these techniques. Setting all
five to zero retains the exhaustive portable
C++ path on the same architecture. The build helper's `--reference-encoder`
produces this oracle separately from the production assets. Complete LPX/PCM
is checked against the pinned shipped exhaustive module. The experiments retain
exact binary hashes; C code layout changes can change the oracle's WASM hash.

[The retained experiment](../../research/web-encoder-exact-search-2026-11-22/README.md)
contains workloads, before/after timings, raw runs, compiler flags, hashes and
reproduction commands. Differential tests compare LPX bytes and decoded PCM
against the pinned pre-optimization module; every encode also performs the
unchanged full shared-C model validation and strict EOF check. These host V8
measurements do not establish another browser/CPU's speed or AVR audio timing.
