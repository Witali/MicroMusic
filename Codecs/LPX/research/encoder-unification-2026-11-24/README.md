# LPX encoder unification validation

Baseline: `b428477f5e4f39797dc7c91b53c01469d7b4944f`. The five stages in the
[execution plan](../../ENCODER_UNIFICATION_PLAN_RU.md) preserve complete LPX/PCM
outputs while removing the duplicate accuracy seed fit, separating budget
policies, sharing bounded candidate evaluation, owning seed state explicitly
and consolidating native/WASM build composition. The
[ownership contract](../../01_ACTIVE_Q0_CODEC/host/ENCODER_UNIFICATION.md)
describes API lifetimes and limits.

## Correctness and packaging

The full 151-test LPX matrix produced 136 passes, 14 optional skips and one
environment failure: the sandbox denied creating a Windows junction for the
existing output-protection test. That unchanged test passed when rerun alone
with junction access. Thus 137 distinct checks passed; the 14 optional checks
were not executed. No assertion or expected output was relaxed.

The executed checks include native CPU/CUDA and scalar/SIMD output equality,
all four accuracy allocations and all three rates, actual GPU encoding,
normalization, malformed inputs/reuse, V9 Long continuation, streaming memory
bounds, full-stream EOF validation and the shipped Worker. The independent
36-request regression compares final accuracy bytes/PCM or the same baseline
no-fit error on silence, tone and clipping at 8/12/16 kHz. Extremely short or
source-dependent no-fit behavior is preserved, not silently repaired here.

The ownership selftest interleaves two complete seed searches while releasing
and reallocating the other context. Cache selftests distinguish identical
packets with different continuation/synthesis state, and check the key budget.
They pass on scalar/SIMD WASM. Existing exhaustive, prefix, analysis and SIMD
kernel tests also pass. Optional skips concern independent native input,
bitrate, decoder/loudness/metric helpers, frozen/Python numerical oracles and
the separate exhaustive CUDA kernel sweep; actual GPU CLI parity did execute.

The standalone application export contains the new transport-policy module;
all 16 relative JavaScript imports resolve. The control, automatic-SIMD and
compact-prefix research probes reproduce and pass their direct kernel tests.
The probe retains historical source-layout support and also accepts the
hash-bound `--working-tree` mode for uncommitted builds. No Site was deployed.

## Paired scalar WASM timing

The [final receipt](benchmark.json) retains all seven alternating warm timings
after three warm-up encodes per module. Inputs are the same deterministic,
frame-aligned synthetic PCM; calls=4. The benchmark asserts compiler/flag
equality and complete output equality. It includes search and validation but
excludes module loading and audio preparation. Node 22.22.3, Windows x64,
Emscripten 6.0.12/Clang 24, C++11, `-O3 -ffp-contract=off` were used.

| Accuracy / rate / samples | Before median ms | After median ms | Before / after |
| --- | ---: | ---: | ---: |
| P3 / 8000 / 640 | 90.75 | 93.59 | 0.970 |
| P4 / 12000 / 2560 | 474.65 | 487.64 | 0.973 |
| P6 / 16000 / 640 | 426.73 | 388.76 | 1.098 |
| P8 / 8000 / 2560 | 2290.57 | 2072.26 | 1.105 |

These four short synthetic workloads do not establish a universal speedup.
The initial three-sample [pilot](pilot-benchmark.json) had substantial timing
spread and mixed results, so the longer warm run was retained alongside it.
P3/P4 show no improvement in the final medians; P6/P8 are approximately 10%
faster in that run, with considerable spread. Removing a seed fit is a proven
reduction in repeated work, not a promise of faster encoding for every source,
backend or duration. No audible-quality gain is claimed.

## Artifact costs

| Artifact | Baseline bytes | Final bytes |
| --- | ---: | ---: |
| Scalar seed WASM | 48343 | 50355 |
| SIMD seed WASM | 51052 | 53042 |
| Scalar adaptive WASM | 425416 | 427430 |
| SIMD adaptive WASM | 433079 | 435735 |
| Native CPU executable, matched local build | 613376 | 647168 |

Explicit ownership and the bounded summary cache add code. Full-search memory
still scales with the input; the cache stores at most eight metric summaries
plus 64 KiB of exact packet keys, not all reconstructed PCM. No MCU decoder or
firmware is changed, and these host checks establish no AVR interrupt/timing
profile. CUDA retains one persistent stream and explicit CPU selection;
batching remains a separate profiling hypothesis.

## Reproduction

Use the existing SDK without installing or changing it. From the checkout root:

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk <sdk> --reference-encoder --prefix-selftest --analysis-selftest --simd-selftest
node web-player/scripts/build-lpx-unification-tests.mjs --emsdk <sdk>
node web-player/scripts/build-lpx-accuracy-tests.mjs --emsdk <sdk>
node web-player/scripts/build-lpx-native.mjs --compiler <clang++> --cuda --nvcc <nvcc> --arch sm_120
```

The verified GPU was an RTX 5060 Ti (SM 12.0), with CUDA 13.3. In a sandbox
whose temporary path contains characters NVCC cannot handle, set process-local
`TEMP` and `TMP` to an ordinary directory under this checkout's ignored `build`
folder before invoking the native helper. Do not print or retain inherited
environment variables.

For the full matrix set `LPX_NATIVE_ENCODER`/`LPX_ACCURACY_NATIVE` to the CPU
executable and `LPX_CUDA_ENCODER`/`LPX_ACCURACY_CUDA` to the CUDA executable.
Set `LPX_UNIFICATION_SELFTEST=1`; point `LPX_EXHAUSTIVE_WASM`,
`LPX_PREFIX_SELFTEST_WASM`, `LPX_ANALYSIS_SELFTEST_WASM`, `LPX_SIMD_SELFTEST_WASM`
and `LPX_ACCURACY_ALLOCATION_SCALAR`/`SIMD` at the corresponding built modules.

```powershell
$lpxTests = Get-ChildItem web-player/tests/lpx-*.test.mjs | ForEach-Object FullName
node --test --test-concurrency=3 $lpxTests
node web-player/scripts/probe-lpx-backends.mjs --working-tree --emsdk <sdk>
node web-player/scripts/export-lpx-site.mjs
node web-player/scripts/benchmark-lpx-unification.mjs
```

Run the benchmark after other builds/tests have ended. Its output remains in
ignored `build/`; the retained receipts here contain synthetic results only,
with no recording filenames, personal paths, environment dumps or private media.
