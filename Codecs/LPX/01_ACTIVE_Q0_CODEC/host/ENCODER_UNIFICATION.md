# LPX encoder ownership and shared policies

Native CPU/CUDA and scalar/SIMD WASM retain the same encoder and V9/Long syntax.
The [execution plan](../../ENCODER_UNIFICATION_PLAN_RU.md) records the steps and
the paired [validation](../../research/encoder-unification-2026-11-24/README.md)
records their measured scope.

| Responsibility | Owner |
| --- | --- |
| Precision, strict bitrate, wire profile and budget kind | `LpxEncodingPolicy.h` |
| Browser transport interpretation of compatibility profiles | `web-player/lpx/encoding-policy.js` |
| Seed search state, prefix history and workspace | `SeedEncoder` in `LpxEncoderContext.h` |
| Actual-rate source analysis and bounded candidate summaries | `CandidateEvaluation` |
| Candidate ordering and the legacy 8 kHz objective | `LpxAdaptiveController.cpp` |
| Frozen whole-output admission and pitch guards | `LpxProfileQuality.cpp` |
| Shared source lists, dependencies, defines and strict FP settings | `web-player/scripts/lib/lpx-build.mjs` |

## Seed reuse and context lifetime

`encodeAccuracy` passes its original admissible fixed-pre/.97 seed into the
adaptive controller. This seed belongs to the exact prepared PCM and prefix;
level preparation must not run again. Canonicalization/correction proposals do
not replace the protected original seed. Seed candidates, first-winner ties,
integer synthesis and decoder verification retain their original semantics.
Accuracy-mode safety recovery may change an unsafe seed before it becomes
the protected control; see [the shared recovery contract](ACCURACY.md).

The C ABI uses one default `SeedEncoder`. C++ host callers can own contexts and
pass one to `fitSeed(..., prefix, &encoder)` after reserving its input size.
Raw `LpxSeedView` pointers expire only on that context's reserve/begin or release.
Separate contexts can interleave complete 160-sample search steps. Native and
adaptive-WASM contexts release owned storage on destruction; freestanding
callers also have explicit `release()`. Analysis tables are shared read-only
after initialization; the uncached oracle retains its separate calculation.

This does not make the default adaptive C ABI concurrent. CUDA still has one
caller/device and one persistent stream per process. Use separate workers or
processes for independent high-level encodes requiring concurrency. Backend
selection remains explicit; portable C++ is the default, and SIMD/CUDA do not
silently replace an explicitly requested backend.

## Candidate evaluation lifetime and bounds

One `CandidateEvaluation` belongs to an immutable reference object, sample rate,
speech policy and [PCM/PWM quality target](QUALITY_TARGET.md). It can share actual-rate reference analysis across quality,
joint and final-selection stages. Each stage still freezes its own incumbent;
relative objectives are never reused as if their denominators were identical.
Legacy controller measurements remain a separate 8 kHz contract.

The cache retains at most eight summaries and 65536 bytes of exact packed keys.
It never retains candidate PCM. Large keys bypass storage. Keys additionally
include the continuation flag, preceding spectrum and complete synthesis state;
wire equality alone cannot establish continuous-output equality. A target
mismatch is rejected before cache lookup. Entries are
discarded with the session, so another source/rate cannot inherit them.

A reused evaluation can avoid synthesis, metrics and repeated intermediate
verification. The final selected stream still undergoes independent complete
decoder verification, including EOF; streaming retains assembled-output checks.
Full-search working buffers and final quality admission still scale with input
length. This is not a constant-memory conversion claim.

## Build contract

Both build helpers import the same codec composition and numeric definitions.
Native ABI/CRT/CUDA flags and WASM exports/linker settings remain platform-owned.
The shared build module itself is hashed in each manifest, along with sources,
headers, resampling tables, licenses and the existing Python oracle provenance.
No Python runtime is introduced.

These are host C++11 techniques (C++17 for the Windows native build). No MCU
decoder, device register definitions or handwritten assembly are changed; host
results establish no AVR timing, interrupt headroom or audible-quality gain.
