# LPX V9 shared pre-impulse states, 2026-11-22

Plan item 3 is implemented: compute the no-impulse prefix once per
subframe/scale/gain and resume each candidate at its pulse position. The cache
stores complete filter/de-emphasis/excitation-ring state and cumulative error
before each of 20 samples. Bound checks, strict first-winner ties, candidate
order and full winner replay are retained. Every emitted stream still passes
complete shared-C PCM/model and EOF validation.

## Additional speed over items 1-2

Baseline is the already pruned/deduplicated module at
`2a06935e600b982ed87e5dd62bc965f4e01a240a`, not the original exhaustive encoder.
Environment: Windows x64, Ryzen 5 5600X, Node 22.22.3 / V8 12.4.254.21-node.56,
Emscripten SDK 6.0.12 / Clang 24, scalar `-O3`, identical compiler flags. No
SIMD, assembly, threading or changes to LPC analysis, packing or decoding.

Median whole-encode milliseconds after two warmups and five paired runs with
alternating execution order; includes input copy, analysis, search, packing,
complete internal C validation and output copy. Byte assertions/external decode
are outside timing. Workloads, source/PCM/output hashes, exact flags, source
hashes and every raw timing are in [measurements.json](measurements.json).

| Workload | Profile | Rate | Items 1-2, ms | With item 3, ms | Additional speedup |
| --- | --- | --- | ---: | ---: | ---: |
| chego speech | P4 | 8 kHz | 41.05 | 30.97 | 1.33x |
| chego speech | P6 | 8 kHz | 325.93 | 174.98 | 1.86x |
| vinni speech | P4 | 8 kHz | 131.79 | 95.95 | 1.37x |
| vinni speech | P6 | 8 kHz | 912.57 | 480.91 | 1.90x |
| chego speech | P4 | 12 kHz | 79.48 | 61.20 | 1.30x |
| chego speech | P6 | 12 kHz | 648.41 | 387.24 | 1.67x |
| chego speech | P4 | 16 kHz | 79.62 | 59.67 | 1.33x |
| chego speech | P6 | 16 kHz | 584.23 | 315.95 | 1.85x |
| Two-tone, 1 s | P4 | 8 kHz | 30.66 | 25.15 | 1.22x |
| Two-tone, 1 s | P6 | 8 kHz | 243.54 | 133.10 | 1.83x |
| Silence, 2 s | P4 | 8 kHz | 22.74 | 21.45 | 1.06x |
| Silence, 2 s | P6 | 8 kHz | 24.66 | 18.78 | 1.31x |
| Two-tone Long, 65537 samples | P4 | 8 kHz | 266.57 | 205.19 | 1.30x |
| Two-tone Long, 65537 samples | P6 | 8 kHz | 1989.27 | 1038.21 | 1.92x |

All 14 cases match complete LPX bytes and decoded PCM exactly. The small silent
P4 difference is close to host timing noise; speech P6 is the main measured
benefit. These results apply to these local V8 workloads, not every browser/CPU
or real-time device. Do not multiply separate experiments' medians to claim a
combined speedup.

The WASM grows from 43198 to 43762 bytes (+564, 1.31%). The static cache costs
21520 bytes per encoder instance, plus alignment; it stays outside the 32 KiB
stack. Existing workspace buffers and sample/memory limits remain unchanged.
This memory tradeoff is reasonable for the bounded Web/PC encoder, not evidence
that the cache is appropriate for AVR firmware.

## Correctness

The full LPX suite passes **63/63 tests, zero skipped**, with native wide/strict
C decoder references, the exhaustive encoder and prefix harness enabled.
The harness executes **918000** direct unbounded/bounded candidate checks over
lags 18/19/20/21/145, gains 0/2/14, zero/unit/nonzero/large scale steps, every
pulse position, amplitudes -8 through +8, ring wrap, nonzero initial histories,
full-scale/clipped PCM and all-zero ties. Unbounded trials compare exact loss
and the complete ring/filter state; bounded trials compare winner classification
and exact state/loss for every candidate that can still win.

The existing 81-case differential suite also compares complete output and PCM
with the original exhaustive module across all rates/profiles, packet tails,
speech and V9 Long. Compiling all three optimization flags as zero still
produces the original exhaustive WASM SHA-256
`f59002ca5e46f6bee2616f28edf3fe61ff91972df93ded823b6af21c64355a49`.
The shared decoder code and binary remain unchanged. Local browser QA converted
8.2 seconds of stereo WAV to a single P4/12 kHz V9 Long file (4671 bytes),
decoded it and played it without console errors.

## Reproduce

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder --prefix-selftest
$env:LPX_EXHAUSTIVE_WASM = (Resolve-Path build/lpx-encoder-exhaustive.wasm).Path
$env:LPX_PREFIX_SELFTEST_WASM = (Resolve-Path build/lpx-prefix-selftest.wasm).Path
node --test web-player/tests/lpx-encoder-exact.test.mjs web-player/tests/lpx-prefix.test.mjs
node web-player/scripts/benchmark-lpx-encoder.mjs --baseline 2a06935e --output build/prefix-repeated.json
```

The benchmark requires installed FFmpeg to read existing retained WAV sources;
it writes only metadata/hashes/timings and never uploads audio. Optional native
decoder setup and full-suite commands are in the
[player README](../../web-player/lpx/README.md) and the
[previous experiment](../web-encoder-exact-search-2026-11-22/README.md).
`LPX_ENCODER_REUSE_PREFIX=0` independently selects the original scalar C trial;
`--reference-encoder` disables all three optimizations. The equivalence argument
and cache lifetime constraints are in the
[WASM cookbook](../../docs/wasm-asm-cookbook/README.md).
