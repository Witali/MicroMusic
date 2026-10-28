# Bounded v5 LPC/excitation trajectories

`refine_speech_trajectory.refine` is a host-only alternative to the existing
conservative `refine_speech_lpc.refine`. It changes neither v5 syntax nor MCU
source. Increasing the old optimizer's settings remains a separate control.

The new algorithm keeps a beam through windows of two to four consecutive
320-sample compact frames. Every branch owns its LPC coefficient trace,
filter history, deemphasis/brightness state and 256-sample pitch ring. LSF
changes include the following frame's exact interpolation tail. Pitch,
primary/optional pulse edits and the existing bounded excitation refit are
crossed with shortlisted LSF alternatives. A first edit need not improve the
objective to survive in the beam; later frames can make that trajectory useful.
Outside a window, the best encountered center seeds the next bounded window.
This is a finite heuristic search, not an optimality or no-fit proof.

All branches use the existing integer `advance` recurrence. Scalar LSF
proposals default to exact bounded local screening (320/640/1280 samples,
including current interpolation and the parent's actual prefix state). The
local screening proxy is unweighted PCM SSE plus exact stored rate; it does
not reset or approximate the state used by final synthesis. Only shortlisted
spectral alternatives are fully reconstructed, crossed with excitation and
ranked. `screening="full"` retains full-suffix scalar screening as an explicit
experimental control. Local screening is heuristic and can miss a candidate
preferred by a full perceptual objective.

Final branch ranking evaluates
the complete reconstructed original-length waveform and the actual serialized
file size, including headers, Rice gap/delta/repeat modes, extras markers and
padding. No weighting state resets at frame boundaries. The original stream
remains eligible whenever it fits the cap. Final exposed alternatives are
checked against native decoding, the independent full model and exact PWM.
Header pre/bright filters stay fixed.

## API

```python
frontier = []
selected, pcm, report, raw = refine(
    reference, blob, decoder, max_bytes,
    frame_limit=8, window_frames=2, beam_width=3,
    spectral_candidates=2, excitation_candidates=2,
    excitation_horizon=80, max_evaluations=512,
    objective=None, objective_name="sse",
    selection="conservative", capacity_policy="amplitude",
    allocation_evaluations=64, rate_lambda=0.0, frontier=frontier,
    screening="local", screening_horizon=640,
)
```

`objective` is a bound callable or object exposing `score(pcm16) -> finite
float`. The default is whole-reference PCM SSE. `SpeechObjective.from_v5` and
`from_chain` provide frozen-seed perceptual weighting; a reset-chain caller
can bind a callback that substitutes the candidate segment into full joined
PCM while keeping perceptual state continuous across decoder resets.

`selection="conservative"` applies the existing full PCM/PWM SSE and STOI
floors against the original segment after search. `selection="objective"`
explicitly permits a metric tradeoff; the report still labels floor failure.
The returned `raw` is the best retained feasible objective alternative, not
necessarily the lowest unweighted SSE or an accepted conservative result.

The optional `frontier` list receives up to 16 nondominated feasible
alternatives with `stream`, `pcm`, `objective`, `file_bytes`, `metrics` and
`conservative_floors_passed`. These alternatives are **not filtered by local
segment floors**. A recording-level caller must join reset segments and judge
whole-reference metrics and the actual combined byte cap. A bounded frontier
is not a proof that a discarded path cannot help another chain combination.
`report["retained_frontier"]` contains numeric metadata, not stream/PCM data.

Caps below the seed's size are allowed. Search can reclaim optional pulses or
find cheaper spectra; an oversized path can remain searchable until later
frames make it feasible. The primary tuple is explicit:

- `selected_feasible`: selected bytes/PCM are present and satisfy the cap.
- `feasible_tradeoff_only`: conservative selection is absent, but `raw` and
  the frontier contain feasible alternatives for whole-recording review.
- `no_feasible_candidate`: both selected and raw are absent; this bounded
  search found no fit and makes no impossibility claim.

Capacity policies are `none`, the previous amplitude-based control, `marginal`,
or a callback with the shared `speech_rate_allocation.reclaim_extras` signature.
Each callback gets exact full-wave render/serialize closures and its path's
prefix boundary. Changing optional fields before that cached boundary is
rejected. The shared full-synthesis limit also bounds allocator render calls.
The separate allocation limit counts the calls actually made by the hook.
Local screening calls and their total synthesized samples are reported
separately from full-wave evaluations. `serialization_calls` counts actual
serializer invocations, including necessary reserialization after reclamation;
an unchanged candidate is not serialized twice. Each shortlist still uses
actual serialization before full ranking and final cap checks.

`rate_lambda` ranks feasible paths by `D + lambda * (8 * actual_file_bytes)` using the shared `distortion_rate`
helper; lambda is per serialized bit, including headers and padding.
Infeasible paths first minimize remaining cap excess. Defaults do not imply
an optimum lambda. A 64-entry full-wave cache, eight quality finalists and a
16-point size/objective frontier bound retained output; each new window has
at most the explicit beam width. Excitation refit uses its existing bounded
local SSE neighborhood as proposal generation even when final ranking is
perceptual, and its separate evaluation count is reported.

## CLI and verification

```text
python tools/refine_speech_trajectory.py reference.wav input.l4hy output --max-bytes 1200 --beam-width 3 --window-frames 2 --evaluations 512
```

The explicit CLI writes selected audio only when feasible, keeps a separate
raw alternative and records no-fit/tradeoff status. Generated media and
private manifests belong in ignored build storage; do not commit them.

`checkpoints` records every started window with `planned_frames`, completed
`frames`, and status `complete` or `evaluation_limit`. An interrupted window
also identifies `interrupted_frame`; partial discovery is never reported as
completed adjacent-frame search. Aggregate complete/incomplete window counts
are explicit.

The regression suite covers a delayed two-frame combination that beam width
one misses, native-exact branch state and partial interpolation tails, real
unpatched joint LPC/excitation improvement against a synthetic target,
oversized seeds, honest finite no-fit, unfiltered frontier export, marginal
allocation, full-length objective hooks, prefix protection and hard synthesis
bounds, independent local-shortlist parity, exact serializer counts and
interrupted-window evidence. Common and compact-only native outputs are checked on the shared
allocation path. These tests prove contracts, not perceptual corpus gains.
Record wall and process CPU time, complete synthesis and local excitation
counts when comparing the new algorithm with default and expanded old search.

For non-speech robustness, pass `speech=False` to `refine` or use CLI
`--non-speech`. The v5 syntax, integer DSP, complete byte cap and state handling
stay the same. Metrics contain PCM/PWM numerical errors with STOI unavailable;
STOI is not computed or used. `quality_kind="non-speech-numerical"` identifies
this scope. Numerical error reduction alone does not establish music quality.
Speech remains the default, with its existing four acceptance floors intact.
