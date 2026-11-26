# Sparse80 scale/gain and pulse joint refinement

Registered 2026-11-26 before implementation and new speech results. Implement
and validate the synthetic mechanism first; speech is permitted only after
the protocol/source/test freeze below. All prior frozen studies remain unchanged.

## Current protected baseline

For every one of the original 27 cases, resolve the authoritative pointer in
`sparse2-speech-v2/case-NNN/result-pointer-private.json`, verify its immutable
receipt and artifact digests, and use its `final-exhaustive.lpx`. This includes
the three admitted changes from the completed study; do not start these cases
again from the old November 2 round-3 stream or import control-arm winners.
Keep the exact saved integer target, original declared auto-quiet policy,
20 speech / 7 negative membership, original 10 heldout speech targets and fixed
STOI eligibility. The complete actual byte count of this current output is B0.

Fresh model/common/v5-only native PCM/PWM and complete baseline metrics must
agree before any new search. The old metrics are agreement checks, not a weaker
admission anchor. Original raw-source paths remain stale; use the already pinned
prepared target bytes unchanged and do not rerun normalization or preprocessing.

## Proposed mechanism and finite space

Select at most TWO complete, nonoverlapping existing 320-sample frames, by
descending current baseline frame PCM SSE, then ascending frame index. Exclude
partial final frames from editing; synthesize and score their unchanged real
tail to EOF. Each frame is edited independently from the same current baseline;
do not chain frame patches or add another pass.

For each selected frame freeze exactly two metadata states where legal:

- M0 is the original `(scaleCode, lag, gainCode)`.
- Enumerate the deduplicated legal Cartesian neighborhood
  `scaleCode + {-1,0,1}` crossed with `gainCode + {-1,0,1}`, with lag fixed.
  Scale code is in 0..31. Gain code is the stored three-bit number in 0..7;
  the decoder's actual gain is `2 * gainCode` in 0,2,...,14. Thus a gain-CODE
  step of one means actual gain changes by two, never an illegal odd gain.
- Rank the at most EIGHT distinct non-incumbent tuples with all original pulse
  fields unchanged, by exact complete PCM SSE through the unchanged suffix.
  Choose the best as M1 even if it loses to M0. Ties use scale code, then gain
  code. M0 is always retained. No source pitch estimate or new lag proposal is
  added; the ignored lag field also stays byte-exact when gain is zero.

The candidate metadata applies to this frame's complete 320 samples only;
subsequent metadata is the original current baseline. Use the true original
incoming h[10], excitation ring[256], dd and cc, including brightness arithmetic.
Never reset state at the editable frame or copy an outgoing state from another
metadata branch.

Sparse80 ALWAYS stores scale5, lag7 and gain3 in every frame, even with gain0.
Gain0-to-2 and gain2-to-0 are legal same-length transitions. No pitch presence
bit or omitted-lag syntax is involved; the original seven lag bits stay exact.

Build ONE common frozen pool of at most THREE distinct symbols for each of the
frame's four existing 80-sample innovations:

1. Retain its original seven-bit symbol.
2. Exhaustively rank all 128 legal symbols with metadata M0 and otherwise
   original pulses, using exact PCM SSE over the next400 real samples, ending
   at EOF if earlier; retain the best.
3. Do the same under M1 with the SAME400-sample rule; retain its best.
4. Deduplicate these three in that order. Fill missing distinct alternatives
   by alternating the M0 and M1 400-sample-SSE ranked lists. Ties prefer the
   incumbent pulse symbol, then ascending seven-bit wire value.

For an innovation after the frame start, obtain its incoming snapshot by
replaying the ORIGINAL earlier pulses of that frame under the corresponding
fixed metadata branch. This snapshot is not the ordinary M0 snapshot for M1.
All pools are completed before evaluating any multi-pulse combination. Both
metadata states and every control use these IDENTICAL pools. The alphabet stays
64 positions `c + ((c + 2) >> 2)` and amplitude -8/+7; zero and positive8 are
not Sparse80 innovations.

Evaluate the complete Cartesian grid `2 * 3^4 = 162` points per frame, at most
324 leaves total. Recompute from the original frame-prefix state through the
unchanged suffix to EOF, with the selected metadata and all four selected
pulses applied together. The inner objective is exact complete PCM SSE for
EVERY grid point and control query; there is no prefix-only pruning, clipping
penalty, PWM training loss or new source-dependent threshold. Every unique
serialized leaf must match the independent full model and both native C
reference receivers in all real PCM/PWM samples and EOF metadata.

## Fair controls on the same grid and same objective

Use three independently admitted arms: joint Cartesian, coordinate M-to-P,
and coordinate P-to-M. All start at M0/original pulse tuple and preserve the
same baseline. Treat metadata M as one two-state block and all FOUR pulses P
as one at-most81-state block, not four prefix-pruned subdecisions.

Before each coordinate arm, retain the common axis points M0 crossed with ALL
pulse tuples, plus BOTH metadata states at the original pulse tuple. This
preserves the ordinary PCM-SSE pulse finalist and metadata-only finalist in
both controls. These are candidates, not forced state transitions.

Perform exactly TWO coordinate sweeps, with no early stopping:

- M-to-P: minimize over both M at the current P; then minimize over every P
  at the selected M. Repeat the same pair once.
- P-to-M: minimize over every P at the current M; then minimize over both M
  at the selected P. Repeat once.

Each minimization uses the identical full-suffix PCM-SSE grid. Equal SSE keeps
the current state first, then uses metadata index/pulse-pool lexicographic
order, so equal-cost cycles cannot produce a spurious improvement. Keep all
complete points queried by each arm, including rejected moves. The control's
best queried point is its raw PCM-SSE finalist. The joint arm sees the entire
grid. This compares crossing a finite coordinate basin; it does not claim a
global optimum over all metadata and 128^4 pulse assignments.

For EACH arm separately, take at most TWELVE distinct changed complete points
from its own queried set, ranked by whole PCM SSE, frame index, metadata index
and pulse tuple order. All actual 32,000-sample corpus cases have ample queried
points to fill the same12 cap. Preserve the best generated changed raw point
even if all its points lose to the baseline. No arm gets another arm's winner
for free, and only the baseline is returned when no changed point is admitted.

Common exact point measurements may be cached by ordered bytes + exact target
+ speech/group/source context, with original creating-event provenance. Report
per-arm proposal attempts AND actual unique complete metric evaluations. There
is no wall/CPU equivalence claim from sharing the grid or cache.

## Complete output admission and immutable bits

Use exactly the completed study's strict complete-output equations and current
B0: both PCM/PWM SSE and available STOI non-regression, both frozen-source voice
floors, clipping, PWM band totals/burst maxima/EVERY partial tail-window floor,
changed actual PWM and strict old mean-joint and PWM-joint improvement. Each
arm is admitted independently against the SAME latest current baseline.

Patch original bit locations, preserving nonminimal legal spectral Rice
spelling, complete actual B0, payload/header sizes, spectra, lag fields, pre,
brightness, unused final bits and every non-editable symbol. Editable fields
are scaleCode5, gainCode3 and the four existing seven-bit innovations in one
selected frame. No new syntax, coefficient, filter, lag, target gain, extras,
packet count, padding, decoder, MCU arithmetic or default is introduced.

## Costs and validation before speech

With two selected frames, metadata screening is at most16 complete suffix
renders. Pulse pool screening is at most2 * 2 * 4 * 128 = 2048 bounded400-sample
renders. Pool generation is a shared heuristic; identical FULL-suffix ranking
is required for leaves and both coordinate controls, not for selecting these
heuristic symbol pools. This keeps the old2048-screen/324-leaf envelope but is
not a matched-CPU claim: metadata screens and branch snapshots are extra work.
For n <=64,000, screen upper bounds are1,024,000 metadata samples and
819,200 pulse-screen samples, plus at most1,920 samples to establish
metadata-conditional pulse snapshots. Main leaves add at most20,736,000 suffix
samples, independent model checks and both native receivers/domains separately.
Count the common baseline separately. Up to323 distinct native streams occur
for two full grids, since their original-baseline point is duplicated.

Per frame each coordinate arm has83 common-axis query attempts and
2 * (2 + 81) =166 block-minimization query attempts, with explicit duplicates;
at most498 lookup attempts per arm over two frames. Exact shared-grid lookups
do not hide their conceptual per-arm query set, and are not new audio renders.
At most36 per-arm complete metric proposal attempts plus the common baseline
are allowed. Actual unique measurements can be fewer through exact caching.
Separate synthesis, pool setup, cache, metrics, persistence, independent audit,
Python-process CPU and total wall time; native WSL CPU is not Python CPU.

Before any speech call, validate one deterministic actual-recurrence joint
rescue: the original state is a coordinate-local PCM-SSE minimum on BOTH axes,
both full-objective coordinate arms fail to leave it, but an M1/non-original-P
grid point strictly lowers complete PCM SSE. All common-pool, field, native
PCM/PWM and EOF assertions must pass. This is a synthetic mechanism witness,
not an audible gain. Also test edges of scale/gain codes, zero steps, nonzero
brightness, gain0-to-2 and gain2-to-0 with unchanged stored lag bits, saturation,
carried pitch state, nonminimal Rice spelling,
partial tails and immutable exact byte masks. If no witness is established,
do not silently call an arbitrary better joint leaf a proven coordinate rescue.

After protocol/source/test freeze, reuse the original first tuning case only
for infrastructure, then all27 current baselines once without tuning. Preserve
the pilot as one case, all missing/unassessed scores and all original group
denominators. Private payloads/paths/stream or target hashes remain ignored;
public evidence contains anonymous numerical summaries only. No perceptual,
AVR interrupt timing or physical-board claim follows from host/native success.

## Code locations and novelty boundary

- Existing initial joint parameter/greedy-pulse fits:
  `tools/encode_low_bitrate_speech.py::search_excitation`, `fit_block`.
- Existing source-F0/gain-floor chains with greedy pulse fits:
  `research/low-bitrate-speech-2026-11-02/pitch_proposals.py::constrained_chain`.
- Existing sequential coordinate parameter/pulse moves for v4/P4/P6:
  `tools/refine_speech_v4.py::optimize_group`.
- Existing pulse beams with fixed metadata:
  `research/low-bitrate-speech-2026-11-02/beam_innovations.py::search_beam` and
  `tools/enhance_sparse80.py::beam`.
- Existing recent exact four-pulse Cartesian, with fixed metadata:
  `experimental/compact-quality/sparse2/exhaustive.py::search`.
- Exact general state arithmetic, including brightness:
  `tools/enhance_speech_compact.py::advance`.
- Actual metadata wire layout:
  `tools/speech_sparse80.py::pack`, `unpack`.

The proposed distinction is finite metadata/pulse Cartesian crossing with
identical full-suffix objective and identical pulse space for coordinate
controls. Merely adding scale/gain neighbors, a wider pulse beam, a source-lag
round or another fixed-metadata pass would not be a new mechanism. No complete
matching Sparse80 operator was found in the inspected sources; this is a scoped
code/history finding, not a claim that joint CELP optimization is novel research.

Implementation would live in a NEW experimental folder; import only read-only
arithmetic/native/admission helpers. Do not edit frozen prior source files or
reuse old `run_campaign.prepare` unchanged: that function intentionally binds
the OLD round3 baseline rather than the required latest `final-exhaustive` B0.
