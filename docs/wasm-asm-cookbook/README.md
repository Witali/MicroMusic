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

### Fallback and evidence

`LPX_ENCODER_ENABLE_PRUNING=0`, `LPX_ENCODER_DEDUP_CANDIDATES=0` and
`LPX_ENCODER_REUSE_PREFIX=0` independently disable these techniques. Setting all
three to zero retains the exhaustive portable
C++ path on the same architecture. The build helper's `--reference-encoder`
produces this oracle separately from the production assets. In the recorded
toolchain its binary SHA-256 equals the previously shipped encoder exactly.

[The retained experiment](../../research/web-encoder-exact-search-2026-11-22/README.md)
contains workloads, before/after timings, raw runs, compiler flags, hashes and
reproduction commands. Differential tests compare LPX bytes and decoded PCM
against the pinned pre-optimization module; every encode also performs the
unchanged full shared-C model validation and strict EOF check. These host V8
measurements do not establish another browser/CPU's speed or AVR audio timing.
