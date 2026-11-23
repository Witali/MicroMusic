# One encoder, four precision allocations

`encodeAccuracy(reference, level, rate, report, calls, prefix)` is the shared
portable C++ entry for P3/P4/P6/P8. The numeric level selects a policy, not a
second encoder or a literal number of bits per sample. Native CPU/CUDA and
scalar/SIMD WASM use the same policy, source analysis, integer synthesis,
adaptive proposals, whole-output admission and packet writer.

| Preset | Existing V9 alphabet | Spectral precision | Extra detail search |
| --- | --- | --- | --- |
| P3 | P4 | Even rank-residual grid and temporal dead zone | No sparse correction layer |
| P4 | P4 | Established 5-bit LSF grid | Common adaptive LPC/excitation search |
| P6 | P6 | Established 6-bit LSF grid | Common adaptive LPC/excitation search |
| P8 | P6 | Same stable 10-LPC model | Additional legal sparse correction parameters |

P4/P6 names and wire syntax are retained. Their new accuracy-mode search may
improve; exact legacy API behavior is independently retained. All four presets
write the existing V9/V9 Long structure. P8 does not recursively finish P6 or
produce a companion file. LPC order and spectral refresh cadence are unchanged.

## Allocation and significance

The nominal allocation is `40 * level` bits per 320-sample analysis frame,
rounded to complete frames, plus the actual 13/17-byte V9 header. The effective
budget is the larger of that allocation and the complete original admissible
quantized seed. This explicit seed floor prevents truncation or infeasible
short-file failures. It is not the retired strict 3/8 kbit/s API: packet rounding,
seed requirements, source-dependent repeats and sample rate affect the result.
At 12/16 kHz the same parameter cadence spends more bits per second.

The common controller generates LPC, pitch, gain and excitation proposals.
P8 also tests legal positions/amplitudes around the largest local reconstruction
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

The internal legacy controller still accounts v5 bytes. Its `budget+9` search
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
byte carry across 20480-sample windows. Only EOF pads the final packet. P8's
correction-fields flag is known from the first header. Final assembled quality
admission protects the current profile's continuous fast control, including
boundary-crossing pitch windows. An allocation failure retains a completely
decoded and verified control. Full/refined admission can still hold whole-file
PCM in WASM; only the fast window path has bounded model working memory.

The incremental verification decoder keeps only a compressed file plus a
20480-sample PCM window. Its exported static C++ state is initialized exactly
once with `__wasm_call_ctors`, before any exported getter/read. Tests cover
arbitrary read sizes, EOF corruption, reuse and Long sample counts.

See the [paired evidence](../../research/unified-accuracy-2026-11-23/README.md).
Objective improvements alone are not evidence of audible gains. The archived
AVR activation study there is explicitly a previous FAST pair, not final-policy
support or arbitrary-stream timing evidence.
