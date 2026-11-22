# Explicit LPX pulse SIMD and backend selection, 2026-11-22

The page now offers **Auto / Ordinary / SIMD**, shows the actual backend and
encoding time, and produces the same complete LPX stream in every mode. Auto
validates WebAssembly SIMD support before loading the SIMD module; unsupported
runtimes use ordinary C/WASM. Auto also falls back on module loading or
instantiation errors. Explicit SIMD reports an error instead of silently
switching; encoding/model-validation errors are never hidden by fallback.

## Four candidates instead of an automatic compiler flag

The earlier `-msimd128` experiment alone did not produce a stable gain. This
kernel changes the organization of pulse trials: four independent amplitudes
share a prefix and execute in i32 lanes, with two f64 pairs for exact loss.
Candidates use the same integer shifts/clips and sample-order loss accumulation.
Winner selection still examines candidates in original order with strict `<`.
Every winner is replayed completely by the original scalar trial, and the full
emitted file still passes shared-C PCM/model and strict EOF validation.

The explicit backend avoids copying 256-slot rings for losing candidates. With
lags 18..145, only generated samples 0/1 can feed back within a 20-sample trial;
their two vectors are retained, and other delays read the passed prefix ring.
A batch may retain a looser incumbent than sequential trials, but it can only
do extra losing work: a rejection cannot beat a subsequently smaller incumbent.
P4 uses its two amplitudes in duplicated lanes; P6 uses four groups of four.

`LPX_ENCODER_SIMD_SEARCH=0` defaults to portable scalar C, even on a SIMD-capable
target. The SIMD artifact explicitly defines it as 1 with `-msimd128`; the
intrinsics require real wasm/SIMD compiler macros and prefix reuse. Other builds
use C. Both artifacts share the C ABI, workspace limits and continuous V9/Long
format. No threads, relaxed SIMD, fast math or new hosting headers are used.

## Whole-encode measurements

Compare the ordinary encoder shipped at
`19bc745555d8678962e5defe1778b295c0eb6ac8` against the explicit SIMD artifact.
Windows x64, Ryzen 5 5600X, Node 22.22.3 / V8 12.4.254.21-node.56, pinned
Emscripten SDK 6.0.12 / Clang 24. Whole synchronous encoder calls include reserve,
input copy, analysis, search, packing, full C verification and output copy.
Two warmups followed by five alternating paired calls give warm medians. Five
additional paired fresh-instance first encodes include cache setup/memory growth
but exclude instantiation. No other benchmark runs concurrently. Assertions and
external PCM decode are outside timing. All flags/hashes/raw runs are retained
in [measurements.json](measurements.json).

| Workload | Profile/rate | Warm ordinary → SIMD, ms | Warm speedup | First encode ordinary → SIMD, ms |
| --- | --- | ---: | ---: | ---: |
| chego speech | P4/8 kHz | 24.26 → 15.37 | 1.58x | 24.39 → 15.51 |
| chego speech | P6/8 kHz | 166.09 → 45.60 | 3.64x | 168.31 → 46.24 |
| vinni speech | P4/8 kHz | 66.75 → 43.06 | 1.55x | 67.34 → 43.33 |
| vinni speech | P6/8 kHz | 474.72 → 135.54 | 3.50x | 473.50 → 131.91 |
| chego speech | P4/12 kHz | 70.06 → 36.14 | 1.94x | 54.40 → 31.88 |
| chego speech | P6/12 kHz | 384.34 → 93.91 | 4.09x | 381.63 → 94.64 |
| chego speech | P4/16 kHz | 46.02 → 29.89 | 1.54x | 46.40 → 29.97 |
| chego speech | P6/16 kHz | 300.37 → 82.75 | 3.63x | 302.97 → 83.94 |
| Two-tone, 1 s | P4/8 kHz | 18.05 → 11.52 | 1.57x | 18.37 → 11.74 |
| Two-tone, 1 s | P6/8 kHz | 116.51 → 31.23 | 3.73x | 118.09 → 31.50 |
| Silence, 2 s | P4/8 kHz | 3.94 → 5.25 | 0.75x | 5.19 → 6.55 |
| Silence, 2 s | P6/8 kHz | 4.00 → 3.93 | 1.02x | 4.19 → 4.40 |
| Two-tone Long, 65537 samples | P4/8 kHz | 145.72 → 95.18 | 1.53x | 150.48 → 96.07 |
| Two-tone Long, 65537 samples | P6/8 kHz | 964.61 → 256.21 | 3.76x | 969.74 → 259.37 |

First-encode speech gains are 1.55-1.71x for P4 and 3.59-4.03x for P6 on this
corpus. Do not generalize them to another CPU/browser or multiply medians from
separate experiments. All 14 cases have identical LPX bytes and decoded PCM.
Silence bypasses pulse search, so it should not benefit from this kernel. The
noisy P4 silence case was repeated separately: 15 warm pairs yielded medians
3.913/3.866 ms, seven fresh pairs 4.135/4.146 ms (ordinary/SIMD). P6 was also
approximately neutral. The initial result remains in measurements.json; the
bounded repeat is retained in [silence-followup.json](silence-followup.json), with its
[reproduction script](silence-followup.mjs).

The ordinary binary remains 43922 bytes with the same SHA-256 as the comparator.
The SIMD binary is 46370 bytes (+2448, 5.6%). The web loader requests only the
selected backend; Auto requests ordinary as well if SIMD initialization fails.
Existing large analysis/prefix caches and memory/sample limits are retained;
the kernel uses transient vector history instead of per-loser ring copies.

## Validation and reproduction

**73/73 LPX tests passed, zero skipped**, including the independent native wide
and strict C references, exhaustive fallback, 918000 existing prefix checks,
analysis/silence harnesses and 972000 new SIMD lane/bound comparisons. The SIMD
harness covers lag 18/19 feedback, ring wrap, all amplitudes/positions, clipping,
extreme LPC coefficients, zero ties and bounds equal to the incumbent.
The separate 87-case differential suite passed against the SIMD binary, with
complete byte and PCM equality to the pinned exhaustive implementation.

Backend tests cover manual selection, support detection, Auto initialization
fallback, explicit SIMD errors, and absence of fallback on encoding failures.
Browser QA exercised Ordinary, SIMD and Auto on an 8.2-second stereo WAV; both
manual downloads were 4522-byte V9 Long streams and compared byte for byte.
SIMD playback started without errors. The UI's encoding timer excludes
module loading and browser audio decoding/resampling; it is a per-job observation,
not a controlled benchmark.

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder --prefix-selftest --analysis-selftest --simd-selftest
$env:LPX_EXHAUSTIVE_WASM = (Resolve-Path build/lpx-encoder-exhaustive.wasm).Path
$env:LPX_PREFIX_SELFTEST_WASM = (Resolve-Path build/lpx-prefix-selftest.wasm).Path
$env:LPX_ANALYSIS_SELFTEST_WASM = (Resolve-Path build/lpx-analysis-selftest.wasm).Path
$env:LPX_SIMD_SELFTEST_WASM = (Resolve-Path build/lpx-simd-selftest.wasm).Path
# Enable the native decoder drivers as described in the player README.
$lpxTests = Get-ChildItem web-player/tests/lpx-*.test.mjs | ForEach-Object FullName
node --test $lpxTests
$env:LPX_CANDIDATE_WASM = (Resolve-Path web-player/lpx/encoder-simd.wasm).Path
node --test web-player/tests/lpx-encoder-exact.test.mjs
Remove-Item Env:LPX_CANDIDATE_WASM
node web-player/scripts/benchmark-lpx-encoder.mjs --baseline 19bc7455 --candidate web-player/lpx/encoder-simd.wasm --candidate-manifest web-player/lpx/encoder-simd-build.json --cold --output build/repeated-simd-search.json
node research/web-encoder-simd-search-2026-11-22/silence-followup.mjs
```

The original intrinsic kernel, arithmetic constraints and official references
are retained in the [WASM cookbook](../../docs/wasm-asm-cookbook/README.md).
Audio remains local; no new recordings or temporary browser downloads are
committed or exported to Sites.
