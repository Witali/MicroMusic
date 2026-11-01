# Bounded synthetic causal-position probe

This is a synthetic mechanism probe, not corpus validation or a quality claim.
Preserve the production refitter unchanged and selectable. The source epoch is
654ada49; production tools/tests/src must match that commit. No corpus audio or
encoded corpus stream is read, no initial fit runs, and no target/default change
or target job is part of this task. Closed native metadata/binary source-closure
reuse is allowed, with fingerprints and paths kept private in ignored build.

## Fixed recipe and finite search

Use legal complete v5 streams of 640 samples, profiles 4 and 6, pre=bright=0,
pitch gain 0, lag 40 and one active optional pulse. Probe only samples 200..239,
away from a160-sample parameter boundary, using the real baseline state after
samples 0..199 and horizon 160. Both mandatory pulses in that 40-sample group and
their original amplitudes remain available; no other refit rule changes.

For each profile, enumerate exactly this fixed lexicographic grid:

- Four profile 4 spectral code vectors: [1,3,5,7,9,11,13,15,17,19],
  [1,2,4,6,8,10,13,17,23,29], [0,1,2,3,4,7,12,18,25,31], and
  [2,5,8,11,14,17,20,23,26,29]. Profile 6 doubles each code. Repeat the
  same vector for both compact frames.
- Scales 8,12,16; mandatory first-half position 0,4,8,13,18; original extra
  position 30,39. This is at most 120 cases per profile,240 total, with no new grid.
- All four parameter rows are [scale,40,0]. All 32 mandatory pulses initially
  use position 5 and alternating positive/negative amplitudes 8 for profile 4,
  7 for profile 6. Override pulse 10's position with the chosen position, retaining
  its positive amplitude. All 16 extras are inactive except extra 5, whose
  amplitude is the negative of that positive mandatory pulse and whose position
  is the grid's original-extra position.
- The legal target differs only by relocating extra 5 onto mandatory pulse 10.
  Its excitation cancels that mandatory event before q saturation. Full target
  PCM comes from this exact serialized target, not a fitted or external signal.

Old positions are the largest absolute output-error location within the 40-sample
group and the active original extra's valid +/-1 neighbors. The experimental
path adds the two actual mandatory positions in that group, without neighbors.
Generate a separately named prototype from the exact frozen function with only
this guarded insertion. A disabled insertion must match original fields, bytes
and trial count. Original production code is never edited or monkey-patched.

Before measured cases, warm original/disabled/enabled prototype once per profile
on the grid's first baseline with reference exactly equal to that baseline:
six explicitly paid warm calls, no cancellation-target tuning. Record JIT/setup
wall/process CPU separately. Measured cases start from identical fields/state,
never another path's output. There are at most 480 measured refit calls; rejected
geometry/coverage cases may skip both refits, and all work/costs are reported.

Stop at the first strict counterexample in each profile. Require legal streams,
unclipped baseline/target/results, identical complete bytes and payload bits for
baseline, target, old and experimental outputs, and fixed cap equal to baseline
bytes. Both outputs must retain exactly one active extra. The first excitation
and output difference is the mandatory location; the observed output-error peak
must occur later and the causal position must be absent from the old position
set. Require experimental full 640-sample PCM SSE 0 and old full SSE>0. If no such
case exists within 120 attempts, report that bound honestly; do not retune.

## Validation and interpretation

Full model, common-native and v5-only-native PCM/PWM must agree for every distinct
serialized synthetic endpoint. Validate full prefix state, actual serialization,
header/filter/geometry and complete-file cap. Record actual old/new byte lengths,
payload bits and extra counts, including any rejected case where an extra is
removed. Report returned trial counts and measured CPU for both paths; extra
positions are extra paid work, not a same-CPU improvement. PWM mismatch counts
versus target are reported even if quantization makes a PCM difference invisible.

With gain, pre and bright zero and no clipping, LPC is the only output-spreading
stage in this recipe. This can establish a missing causal candidate position,
not a general optimality, robustness, perceptual, bitrate or corpus benefit.
Retain all attempts privately, commit only the compact reproducible synthetic
recipe/numeric results after privacy checks, and do not push.
