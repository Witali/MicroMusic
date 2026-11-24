# Common LPX parameter selection and timbre recovery

Baseline: `f1f9a0d9fc76fdc52f5787b54f2ba5471bd3db8c`. The retained
[synthetic results](synthetic-results.json) identify the exact old/current
WASM hashes and individual measurements. No recorded media, source names,
private paths, recording fingerprints or per-recording results are distributed.

## Problem and implementation

Ordered LSFs do not guarantee stable rounded Q12 LPC interpolation. Even
frozen stable polynomials can exhibit growth with changing integer filter
coefficients and carried state. Reducing output level alone can leave an
incorrect, moderately loud spectrum.

Accuracy P3/P4/P6/P8 now share:

- Actual interpolated Q12 Schur checks and source-relative rendered-level and
  off-band replacement guards.
- Local effective-order2/4/6/8 recovery through the existing ten-LSF syntax.
  Safe alternatives are compared using actual-rate PCM/PWM magnitude and
  temporal errors. Source analysis is reused. When the failing region grows,
  reconsider the complete order set on its union, up to three passes/32 fits.
  Bounded unexpanded-analysis/local-regularization recovery remains available.
- The same residual-detail operator at every accuracy level. Exact packed
  budgets and complete-output quality admission decide which details survive.
  The internal v5 controller always preserves the admissible control floor;
  final admission independently counts complete V9 bytes.

This is bounded discrete analysis through synthesis, initialized by continuous
LPC analysis. It is not a global optimum. Filter order, pulse amplitudes and
positions are evaluated through the actual quantized integer reconstruction.
No source-specific frequencies, bell detector or profile-specific recovery is
used. Synthesis is never reset or spliced. V9/Long and the MCU decoder remain
unchanged; existing P4/P6 alphabets are not bit-prefix scalable layers.

The native CLI now defaults to the same accuracy engine as the Web UI.
Unsafe optional pre-emphasis/bandwidth seeds are explicitly distinguished from
backend/argument/allocation failures, so a rejected optional variant cannot
invalidate an already admissible control. Genuine failures still propagate.
`--legacy` explicitly retains historical expert search/bitrate behavior;
its pinned legacy WASM and Python-reference checks remain separate.

## Synthetic quality and cost

Seven deterministic families (inharmonic bell, chime, three-tone mixture,
high-pass noise attack, harmonic carrier, high ring and high pair) × three
actual rates8/12/16 kHz × four levels =84 paired fast encodes. No gain or
delay fitting is used. Timing alternates old/current order and records three
warm calls per case. This local run overlapped other validation workloads;
timing is not an isolated throughput or real-time measurement.

| Measurement | Baseline | Current |
| --- | ---: | ---: |
| Cases passing broad gain/tail bounds |65/84 |84/84 |
| Mean spectral shape error on65 previously bounded cases |.08566 |.07872 |
| Mean envelope error on the same65 cases |.05677 |.05135 |
| Sum of encoded bytes |29,742 |30,308 |
| Sum of per-case median scalar encoding times |4.254 s |8.110 s |

Bytes increase1.90%; aggregate median time increases1.91× on this workload.
Recovery deliberately spends additional encoding work on difficult filters.
There is no general speedup claim. No previously bounded case loses a
significant partial or crosses the frozen substantial-regression thresholds:
spectral shape +.05, envelope +.10, minimum partial retention −.10.
Some small metric tradeoffs remain; aggregate improvement is not proof of
transparent or universally improved sound.

Three retained carrier-to-ring transition fixtures add36 level/rate settings.
The later ring is measured separately so successful preceding harmonics cannot
hide its loss. Unchanged gates require spectral shape error below.5 and every
significant partial's amplitude retention at least.5. Scalar/SIMD output is
identical; native CPU and explicit CUDA paths match. A previously valid-input
no-fit on the upper-ring transition is covered by this regression.

An exploratory96-setting transition grid also completed without a no-fit and
passed the same quality thresholds (worst shape.312, minimum retention.534).
The36 retained settings are the maintained regression contract. Synthetic
quality tests do not guarantee intelligibility or transparency for all audio.

## Bandwidth and browser limits

The browser now defaults to16 kHz. An8 kHz source preparation removes content
above4 kHz before the codec; no parameter optimization can recover those
discarded partials.16 kHz retains content below8 kHz, with a larger file.
Fast accuracy streaming/decoding accepts64 million samples, so longer audio
can use16 kHz; full/refined/legacy searches retain32 million. Input remains
capped at100 MiB. Source/verification storage and optional global analysis have
their documented duration-dependent costs; this is not unlimited conversion.

## Reproduction

Use Emscripten6.0.12/Clang24, strict floating-point contraction disabled,
portable C++11 wasm32 and native C++17; optional SIMD128 and CUDA13.3 SM120
retain explicit scalar/CPU selection. No assembly or device timing claim is
introduced. The [cookbook](../../../../docs/wasm-asm-cookbook/README.md)
retains the independent30,015-vector Schur/root check, including exact-integer
resolution of238 near-unit cases: zero disagreements and15 analytical checks.

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder --prefix-selftest --analysis-selftest --simd-selftest
node web-player/scripts/build-lpx-unification-tests.mjs --emsdk C:/path/to/emsdk
node web-player/scripts/build-lpx-accuracy-tests.mjs --emsdk C:/path/to/emsdk
node web-player/scripts/benchmark-lpx-timbre.mjs
node --test web-player/tests/lpx-timbre.test.mjs web-player/tests/lpx-stream-limits.test.mjs
```

The benchmark writes only generated synthetic measurements under ignored
`build/lpx-timbre-benchmark.json`. Native/CUDA parity tests additionally use
`LPX_ACCURACY_NATIVE`, `LPX_ACCURACY_CUDA`, `LPX_NATIVE_ENCODER` and
`LPX_CUDA_ENCODER`. Legacy golden revisions are retained unchanged; new
accuracy behavior is protected by independent quality gates, deterministic
backends, metadata/history invariants and complete decoder verification.

## Final validation

The full LPX run completed175 tests:161 passed,14 optional helper tests skipped,
zero failures. After the final explicit-unsafe status handling and exact-zero
SSE pruning, all60 affected accuracy, legacy/native CLI, timbre, streaming,
limits, budget and ownership/allocation checks passed with no skips. This
includes the real optional-seed regression at16 kHz/P3, formerly a fatal no-fit.
All native CPU/CUDA and scalar/SIMD build inputs/artifact hashes match.
The static export resolves all18 relative imports and contains no retired
hosting JSON. These checks establish host correctness, not MCU real-time or
arbitrary-audio transparency.
