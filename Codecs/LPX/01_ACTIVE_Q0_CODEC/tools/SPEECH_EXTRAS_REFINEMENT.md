# Shared optional-pulse group refinement

`refine_speech_extras.refit_extra_group` owns the cheap 40-sample optional phase
used by `refine_speech_lpc.adapt_excitation`. It imports the existing integer
replay and SSE functions, without importing an LPC or controller caller.

Callers provide validated fields, the real prefix history/filter/pitch state,
the current active-extra count and capacity. The helper uses its caller-owned
extras array as scratch, restores its original row before normal return, and
returns `(position, amplitude, local_sse, trial_evaluations)`. It never changes
spectra, parameters, mandatory pulses or prefix state. Its score covers only
the supplied lookahead, so full-record native checks and admission remain the
caller's responsibility.

The default policy preserves the original peak-error position, active-extra
neighbors, amplitude neighborhood, ascending iteration and strict-improvement
ties. Twelve pre-extraction cases across both profiles, nonzero prefix starts
and one-sample tails retain exact fields, bytes, counts and full SSE. The LPC
caller continues to use this default.

Explicit `causal_positions=True` also includes the two mandatory-pulse locations
that lie inside the played group. It does not widen the amplitude set or enable
a controller/default mode. The P4 cancellation fixture in the
[synthetic probe](../../research/v5-causal-extra-probe-2026-11-01/README.md) now
also passes through this shared helper while all base fields remain frozen.
Both optional-only controls use 57 complete bytes: legacy requires 29 trials
and fails to reproduce the target, while causal positions require 43 and
recover exact full native/model PCM/PWM. These counts differ from the probe's
43/57 **full joint-refit** counts, which include mandatory-pulse work.

This is a synthetic coverage result, with no natural-speech, audible, AVR timing
or linked-Flash claim. Existing P6/default callers keep their legacy policy.

The wide `refine_speech_excitation.optimize_group` and all-position
`enhance_speech_compact.proposals` retain their different policies. They cannot
replace this narrow phase without changing additional fields or search rules.

## Full-record existing-extra pass

`refine_existing_extras(reference, blob, decoder, *, max_bytes, ...)` is a
separate P4-only API. It visits only initially active played extras:
`amplitude != 0 and group * 40 + position < samples`. It preserves inactive and
unplayed pulses, spectrum, parameters, mandatory pulses, geometry and the first
20 header bytes. `force_extras` retains the original flag even after removing
the last played extra. Only the payload-length header field changes as needed.
Each serialized checkpoint is checked against both the requested cap and the
original file length. Zero-amplitude position aliases denote no pulse.

The forward working state advances through untouched gaps and each edited
group using the entire live extras array; future extras are not zeroed. The
working trajectory can become worse globally despite a local lookahead gain.
The original and every completed full checkpoint are retained independently.
`causal_positions=False` supplies the legacy-position control, and `True` adds
the tested mandatory locations without widening amplitudes or enabling a
default controller operator. P6 inputs to this new pass are rejected explicitly.

Four checkpoints by default use fixed eligible-group coverage fractions. Exact
byte deduplication may map several slots to the same candidate. Candidate
coverage metadata records its first publication; checkpoint rows record their
actual later coverage. Every distinct full stream is serialized, scored on the
complete PCM and verified against the model and native PCM/PWM before
`candidate_sink(stream, integer_full_sse)` or another quota check. An
interruption between fixed checkpoints publishes its completed final working
snapshot during separately charged finalization. Missing slots are explicit
`partial_fallback` entries; they never claim completed coverage.

The default trial allowance is `49 * eligible_active_groups`. The conservative
atomic bounds are 33 trials for legacy positions and 49 for causal positions.
An optional CPU quota is cooperative between groups; setup/publication can
overshoot and final verification runs afterward. Reports separate those clocks
and count actual trials, state replay and complete synthesis. Zero-error/no-active
shortcuts preserve the original and report zero visited groups. Spatial eligible/
visited index lists are private source-derived evidence; strip them from public
corpus projections.

The returned tuple is `(selected_stream, selected_pcm, report, raw_stream)`.
Selection here applies only full PCM/PWM SSE/STOI floors, retaining baseline
rollback. A corpus/controller caller must additionally apply whole-chain
period, clipping and joint voice/noise admission. Catalogue metric roles are
owned copies. The existing encoder defaults, bitstream and decoder are unchanged.

The [six-context P4 corpus pilot](../../research/v5-existing-extra-pass-2026-11-01/evidence/RESULTS.md)
completed 20 full passes and 36 cap decisions. Neither policy extends the complete
admissible size/joint-score frontier of the prior V1/anchor union. Of 48 distinct
changed whole tuples, 47 fail the unchanged gates and the sole admissible tuple
is dominated by prior evidence. Both policies keep baseline rollback, and neither
is adopted as a new default controller operator. The synthetic cancellation
result establishes candidate coverage, not natural-speech or audible benefit.

## Incremental state and protected blocks

`ExistingExtraPass(reference, blob, *, max_bytes, causal_positions=False,
horizon=160, max_trial_evaluations=None, cpu_seconds=None)` owns the same exact
forward walk used by `refine_existing_extras`. It accepts P4 only and freezes the
initial eligible group order. `step()` consumes the next group or returns false
at the end or before exceeding the conservative atomic trial allowance. A CPU
quota can raise `CpuBudgetExceeded` before a group starts. Zero-error shortcuts,
native verification, whole quality gates and immediate candidate persistence
remain the caller's responsibility for this incremental interface.

`serialize()` returns a complete stream under the original and requested caps;
`synthesize()` returns owned complete PCM from zero state. Neither operation
moves the forward prefix. `snapshot()` owns read-only copies of protected extra
rows and prefix history/filter/pitch state. `rollback(snapshot)` restores those
rows and reconstructs their true DSP state from the saved boundary through the
already consumed current cursor. It restores the live active count but never
refunds trials, coverage, visited groups or cumulative attempted changes. The
next step visits the next originally eligible group, including after a rejection.
Replay is computed before installation; an arithmetic failure leaves live fields
and DSP state intact. Foreign, future or stale snapshots are rejected. A successful
rollback invalidates older snapshots; take a fresh snapshot before the next block.

`changed` counts attempted changed groups, while `committed_changed_groups`
counts current meaningful differences from the original. Read scalar progress
and copy `visited`; consumers must not mutate session-owned state. `work_counts()`
returns an owned dictionary of actual synthesis/serialization/prefix advances,
snapshot/rollback calls and elapsed costs. Rollback replay calls/samples are a
subset of total prefix work, so do not add them twice. Failed replay attempts are
counted separately from completed rollbacks. An interleaved multi-reset caller
must time its actual calls rather than sum overlapping lifetime CPU clocks.

The existing full-pass function retains its original callback, selection and
report contracts. These state methods provide the mechanism for a separate
prospective whole-chain admission/rollback experiment; they establish no corpus,
audible-quality, linked-Flash or target-timing improvement by themselves.
