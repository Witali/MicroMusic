# One encoder, four precision allocations

`encodeAccuracy(reference, level, rate, report, calls, prefix)` is the shared
portable C++ entry for P3/P4/P6/P8. The numeric level selects a policy, not a
second encoder or a literal number of bits per sample. Native CPU/CUDA and
scalar/SIMD WASM use the same policy, source analysis, integer synthesis,
adaptive proposals, whole-output admission and packet writer.

| Preset | Existing V9 alphabet | Spectral precision | Extra detail search |
| --- | --- | --- | --- |
| P3 | P4 | Even rank-residual grid and temporal dead zone | Common budgeted residual corrections |
| P4 | P4 | Established 5-bit LSF grid | Common budgeted residual corrections |
| P6 | P6 | Established 6-bit LSF grid | Common budgeted residual corrections |
| P8 | P6 | Same spectral grid as P6 | Common budgeted residual corrections |

P4/P6 names and wire syntax are retained. Their new accuracy-mode search may
improve; exact legacy API behavior is independently retained. All four presets
write the existing V9/V9 Long structure. P8 does not recursively finish P6 or
produce a companion file. The decoder retains ten LSFs and the same spectral
refresh cadence. The existing P4/P6 alphabets are not literal bit-prefix layers;
truncating a P8 packet does not produce a valid lower-level packet.

## Allocation and significance

The nominal allocation is `40 * level` bits per 320-sample analysis frame,
rounded to complete frames, plus the actual 13/17-byte V9 header. The effective
budget is the larger of that allocation and the complete original admissible
quantized seed. This explicit seed floor prevents truncation or infeasible
short-file failures. It is not the retired strict 3/8 kbit/s API: packet rounding,
seed requirements, source-dependent repeats and sample rate affect the result.
At 12/16 kHz the same parameter cadence spends more bits per second.

The common controller generates LPC, pitch, gain and excitation proposals.
Every level also tests legal positions/amplitudes around the largest local reconstruction
residual over a 160-sample horizon. Proposals are ordered by reconstructed SSE
reduction per added symbol bit, not coefficient magnitude. A new sparse symbol
costs ten payload bits; replacing a present symbol adds none. The first active
correction also enables a presence bit for every actual 40-sample group.
Exact packing measures that first activation, including header flags, presence
bits, spectrum/repeats and padding. A zero-amplitude symbol is inactive even
when its position is nonnegative. Padding is conservatively reserved after
activation during local allocation; final
selection counts exact complete packed bytes. The greedy proposal pass is not
a proof of a globally optimal coefficient subset.

The internal legacy controller still accounts v5 bytes. Its
`max(budget+9, compactBytes(seed))` search
allowance does not admit a file by itself: the common V9 selector independently
requires the complete output to fit the effective current-profile budget.
It freezes each profile's own original admissible seed, checks full decoded
PCM/PWM, actual-rate spectral/time/STOI, voice/noise/clipping and native pitch
windows, and retains the best safe strict improvement under the unchanged
objective. Ties retain the original. Relative scores from successive phases
are never multiplied. P8 is compared with P6 offline; production performs one
profile encode and cannot promise a strict quality increase for every source.

## Continuation and memory

The same policy, quantizer history, complete synthesis state and partial output
byte carry across 20480-sample windows. Only EOF pads the final packet. The
correction-fields flag is known from the first header at every accuracy level.
Final assembled quality
admission protects the current profile's continuous fast control, including
boundary-crossing pitch windows. An allocation failure retains a completely
decoded and verified control. Full/refined admission can still hold whole-file
PCM in WASM; only the fast window path has bounded model working memory.

Fast accuracy streaming accepts up to 64 million samples; whole-input and
streaming-refinement searches retain their 32-million-sample cap. Verification
decoding accepts 64 million samples. Compressed input remains capped at100 MiB;
output storage and optional whole-output quality buffers still grow with length.

## Source-aware synthesis recovery

Accuracy mode checks the actual rounded Q12 LPC vectors, including every
interpolated vector, with a portable Schur step-down test. Ordered LSF endpoints
alone do not guarantee stable interpolated LPC coefficients. Unsafe transitions
are regularized toward the preceding transmitted spectrum. Legacy C ABI search
retains its separately pinned byte contract.

A frozen-polynomial test does not certify a switched integer filter. The seed
therefore also renders from the original carried state and rejects catastrophic
source-relative level growth and added clipping. Its off-band recovery target
compares normalized32-band Hann spectra in512-sample windows,
jointly requiring more than.5 Hellinger error and35% output power in bands
holding less than.5% of source power. It is a generous recovery trigger, not a
general perceptual-quality score. Eligibility uses the same Hann-weighted
source energy as the spectra, normalized by the sum of squared window weights,
with the existing64-PCM-count RMS floor. Raw energy at a window edge cannot
make near-silent windowed spectra eligible. On failure, a shared bounded
recovery tries effective analysis orders2/4/6/8 near the first failing region,
then unexpanded analysis and localized spectral regularization. Ten LSFs are
still transmitted; no new decoder, tone detector or profile-specific fix is
introduced. It never resets or splices synthesis history. Ordinary safe seeds
retain their original analysis. Safe order alternatives are ranked by the sum
of actual-rate balanced magnitude and temporal errors on both PCM and PWM;
the source analysis is reused. When a candidate expands the failing region,
all four orders are reconsidered on the enlarged mask, up to three passes and
32 total fits. This avoids accepting the first safe low-order
filter when another legal partial requires a more complex model. It is bounded
analysis through synthesis of transmitted parameters, not a global optimum.
Target-compliant models remain preferred. If no model meets this local
perceptual target after the bounded search, retain the least actual
magnitude/temporal-error model among all Q12- and source-level-safe attempts,
including the ordinary analysis. A heuristic target is not a file-validity
test for arbitrary lossy audio. A seed with no hard-safe reconstruction still
reports an error. Refinement admission retains the unchanged spectrum gate.

An optional continuously carried refinement can independently lose its safe
seed while the complete control remains valid. Explicit unsafe-seed status
then discards the entire optional candidate; it never splices contexts.
Generic argument, kernel, CUDA and verification failures remain fatal.

Residual and adaptive proposals must pass source-level safety and existing
whole-output quality admission. Independent synthetic tests check harmonic and
inharmonic partial retention, spectral shape, attacks and decaying tails at the
same actual sample rate. These are bounded regression checks, not a guarantee
of transparent coding for arbitrary audio. The browser defaults to16 kHz;
8 kHz necessarily discards source content above4 kHz before LPX search.

The search minimizes reconstructed distortion subject to legal quantized
symbols, complete packed-byte allocation and synthesis safety. Continuous
Levinson analysis supplies an initial estimate; its prediction-error optimum
does not certify the rounded transmitted filter or the nonlinear integer
decoder output. Candidate evaluation uses those actual transmitted parameters.
The [Opus specification's LPC stability discussion](https://www.rfc-editor.org/rfc/rfc6716.html#section-4.2.7.5.8)
also describes why rounded LPC requires explicit checking and why near-unit
classification is numerically difficult. LPX retains its own interpolation,
integer synthesis and independently tested guard.

The incremental verification decoder keeps only a compressed file plus a
20480-sample PCM window. Its exported static C++ state is initialized exactly
once with `__wasm_call_ctors`, before any exported getter/read. Tests cover
arbitrary read sizes, EOF corruption, reuse and Long sample counts.

See the [paired evidence](../../research/unified-accuracy-2026-11-23/README.md).
Objective improvements alone are not evidence of audible gains. The archived
AVR activation study there is explicitly a previous FAST pair, not final-policy
support or arbitrary-stream timing evidence.
