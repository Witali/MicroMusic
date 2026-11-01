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
A separately bounded P4 full-record pass over existing active extras remains
the next implementation step; it must retain the original and every completed
checkpoint independently of its working trajectory. It must keep inactive slots
and unplayed stored fields intact, verify actual serialized caps and apply
whole-record gates.

The wide `refine_speech_excitation.optimize_group` and all-position
`enhance_speech_compact.proposals` retain their different policies. They cannot
replace this narrow phase without changing additional fields or search rules.
