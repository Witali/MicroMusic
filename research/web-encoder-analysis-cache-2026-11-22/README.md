# LPX V9 plan items 4-5, 2026-11-22

Selected production changes: commit strictly silent blocks directly with the
same pulse/ring state; cache exact double terms for the fixed LSF grid and
Hamming window. Bisection, scalar accumulation order, candidate selection,
packing and complete shared-C PCM/model/EOF verification remain unchanged.

## Item 4: silence and LPC/LSF analysis

The comparator is the shipped encoder after items 1-3,
`02a2fea53f9df7b5aa2402c38d58a9a432e4bf50`. Environment: Windows x64,
Ryzen 5 5600X, Node 22.22.3 / V8 12.4.254.21-node.56, Emscripten SDK 6.0.12,
Clang 24, scalar `-O3`, no fast math. Two warmups and five alternating-order
paired whole-encode calls; allocation/input copy, analysis, search, packing,
complete internal C verification and output copy are timed. Assertions and
external decode are outside timing. No other benchmark runs concurrently.

[silence-measurements.json](silence-measurements.json) isolates the shortcut:
4-8% on pure silence, with non-silent changes near host timing noise. The full
[analysis-measurements.json](analysis-measurements.json) records both changes,
all raw runs/flags/source hashes, input/LPX/PCM hashes, and five first encodes
in fresh WASM instances. Instantiation is outside that timing; preparation of
the cache and memory growth are inside. A fresh first encode is relevant to
the page's Worker lifecycle; warm ratios alone overstate its benefit.

| Workload | Profile/rate | Warm before → after, ms | Warm speedup | First encode before → after, ms |
| --- | --- | ---: | ---: | ---: |
| chego speech | P4/8 kHz | 31.48 → 24.18 | 1.30x | 31.37 → 24.52 |
| chego speech | P6/8 kHz | 179.14 → 168.73 | 1.06x | 178.83 → 172.90 |
| vinni speech | P4/8 kHz | 85.57 → 67.04 | 1.28x | 85.56 → 67.61 |
| vinni speech | P6/8 kHz | 500.34 → 472.23 | 1.06x | 487.34 → 478.41 |
| chego speech | P4/12 kHz | 63.61 → 52.22 | 1.22x | 62.22 → 52.24 |
| chego speech | P6/12 kHz | 401.71 → 380.63 | 1.06x | 398.79 → 382.46 |
| chego speech | P4/16 kHz | 61.04 → 46.10 | 1.32x | 62.53 → 48.25 |
| chego speech | P6/16 kHz | 326.19 → 302.83 | 1.08x | 321.87 → 306.27 |
| Two-tone, 1 s | P4/8 kHz | 24.03 → 18.14 | 1.32x | 24.27 → 18.42 |
| Two-tone, 1 s | P6/8 kHz | 125.24 → 117.17 | 1.07x | 123.02 → 120.81 |
| Silence, 2 s | P4/8 kHz | 16.17 → 3.89 | 4.16x | 16.36 → 4.25 |
| Silence, 2 s | P6/8 kHz | 16.72 → 3.90 | 4.28x | 16.54 → 4.35 |
| Two-tone Long, 65537 samples | P4/8 kHz | 195.64 → 145.61 | 1.34x | 194.68 → 148.62 |
| Two-tone Long, 65537 samples | P6/8 kHz | 1023.01 → 946.14 | 1.08x | 1006.36 → 972.90 |

In these first-encode speech cases the additional speedup is 1.19-1.30x for P4
and 1.02-1.05x for P6; pure silence is 3.80-3.85x faster. These are local V8
measurements, not a universal browser/CPU multiplier. All 14 LPX/PCM outputs
match exactly in both warm and fresh-instance runs. Do not multiply medians
from separate experiments to infer a total speedup.

WASM changes from 43762 to 43922 bytes (+160, 0.37%). The runtime grid adds
112816 static bytes (about 110 KiB), plus alignment/ready state, per instance.
It is generated on first use rather than embedded in the download. Existing
workspace buffers, file/sample limits and C decoder stay unchanged. No new
firmware timing/interrupt support is claimed.

## Item 5: SIMD and memory experiments

Both candidates start from the selected scalar source at
`9db7939558b33630d26ae363ea38f37955b185e3`. The control compilation reproduces
its WASM hash exactly. [probe-lpx-backends.mjs](../../web-player/scripts/probe-lpx-backends.mjs)
retains the checked source transformations, compiler flags and direct harnesses.

| Candidate | Size | Measured result | Decision |
| --- | ---: | --- | --- |
| Scalar/full-prefix control | 43922 B | Baseline | Retained |
| Add `-msimd128` | 45670 B | Approximately 0.98-1.02x; no stable gain | Keep as experiment |
| Compact prefix snapshots | 43175 B | Prefix cache 21520 → 1120 B, but non-silent encodes about 23-45% slower | Keep as experiment |

[simd-measurements.json](simd-measurements.json) and
[compact-measurements.json](compact-measurements.json) contain all 14 cases,
timings and complete LPX/PCM hashes for each. The compact variant caches only
filter/de-emphasis history and prefix excitation, rebuilding ring prefixes for
each candidate. That saves 20400 bytes but increases runtime in this build.
Neither candidate is selected by the page. The SIMD result does not establish
the value of a separately designed explicit SIMD kernel or another processor.

## Validation and reproduction

The selected production build passed **66/66 LPX tests, zero skipped**, with
the native wide/strict C references and all optional harnesses enabled. The
stream differential suite now covers 87 input/rate/profile cases, including
leading zeros, long pauses after sound and resumed excitation. Direct checks:
918000 prefix/state/bound cases, 48 complete silent-block state/PCM/pulse cases,
and 20768 bitwise Hamming/grid/root-sum comparisons. Every candidate encode
retains internal shared-C validation. Both experimental variants also passed
the direct harnesses and the full 87-case differential suite.

All five optimizations can be disabled independently. The newly compiled full
oracle has WASM hash `6a3e984bcbb091cf09fa634b2c483bdda538548829916f79623bf6f2d4fe4872`;
its LPX/PCM still matches the pinned original exhaustive encoder exactly.
Code layout changed, so equality of output is checked independently of binary
identity. Local browser QA converted an 8.2-second stereo WAV into one
P6/16 kHz V9 Long stream (9172 bytes), then decoded and played it without errors.

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder --prefix-selftest --analysis-selftest
$env:LPX_EXHAUSTIVE_WASM = (Resolve-Path build/lpx-encoder-exhaustive.wasm).Path
$env:LPX_PREFIX_SELFTEST_WASM = (Resolve-Path build/lpx-prefix-selftest.wasm).Path
$env:LPX_ANALYSIS_SELFTEST_WASM = (Resolve-Path build/lpx-analysis-selftest.wasm).Path
# Set LPX_WSL_REFERENCE and LPX_LEGACY_REFERENCE for the native decoder drivers.
$lpxTests = Get-ChildItem web-player/tests/lpx-*.test.mjs | ForEach-Object FullName
node --test $lpxTests
node web-player/scripts/benchmark-lpx-encoder.mjs --baseline 02a2fea5 --cold --output build/repeated-analysis.json
node web-player/scripts/probe-lpx-backends.mjs --emsdk C:/path/to/emsdk --source-ref 9db79395
node web-player/scripts/benchmark-lpx-encoder.mjs --baseline 9db79395 --candidate build/lpx-backend-probes/simd.wasm --candidate-manifest build/lpx-backend-probes/simd-build.json --output build/repeated-simd.json
node web-player/scripts/benchmark-lpx-encoder.mjs --baseline 9db79395 --candidate build/lpx-backend-probes/compact-prefix.wasm --candidate-manifest build/lpx-backend-probes/compact-prefix-build.json --output build/repeated-compact.json
$env:LPX_CANDIDATE_WASM = (Resolve-Path build/lpx-backend-probes/compact-prefix.wasm).Path
node --test web-player/tests/lpx-encoder-exact.test.mjs
Remove-Item Env:LPX_CANDIDATE_WASM
```

The benchmark requires local FFmpeg. Audio remains local; retained results
contain hashes/timings/provenance, not new recordings. Native decoder setup is
described in the [player README](../../web-player/lpx/README.md). Correctness
constraints and portable fallbacks are in the
[WASM cookbook](../../docs/wasm-asm-cookbook/README.md).
