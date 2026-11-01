# Joint rate allocation: predeclared finite pilot

This is fresh encoder search on unchanged v5 syntax, not a saved-result replay
or a perceptual equivalence test. This protocol precedes new search outcomes.
No decoder, new format, MCU code or default algorithm is part of the pilot.
The future production/harness commit must be frozen before any actual call.

## Existing evidence and common baselines

The previous price sweep used alpha {0,.1,1} on one tuning source and found no
smaller admitted result. Fixed-field exact removal/bounded swaps improved some
same-size amplitude controls but did not preserve their stronger original
incumbent's quality. Parameter-cost sketches are hypothetical new-format costs,
not implemented v5 savings. None of these outcomes counts as a new pilot result.

Use all 104 existing source/domain/profile/declared-level contexts. Within each
context, select the strongest union member from the original canonical100 seed
and the target-admitted matched-CPU100 winners. Rank by joint score, actual
complete bytes, fixed phase priority (default before screen), then fixed arm,
tier and candidate order. Different source levels, profiles or reset geometry
cannot compete. Keep exact old ordered bytes, references and target provenance.
The larger/older canonical source remains a provenance/rollback record.

Rebase B to the actual bytes of the chosen current winner. Reconstruct its
declared target with the frozen level policy and require its exact saved PCM
identity and zero clipping. Preparation performs no decoding, metrics or fits;
fresh model/common/v5 PCM/PWM whole-baseline checks and metric agreement must
pass after source freeze and before that context's first new search. Baseline
preparation, target reconstruction, startup/JIT and all later work have explicit
wall/process CPU accounting; unknown costs are not zero.

## Pilot selection from metadata

Select sources before any new outputs, retain both profiles and full records:

1. Among tuning speech with preserved level, one reset and at least 8,000
   samples, sort by (sample count, ordinal): take the first and middle entries.
2. Take the smallest ordinal among the existing auto-quiet speech sources.
3. Among multi-reset speech, take largest reset count, then largest sample
   count, then smallest ordinal. This is an explicit structural stress case,
   even if its original split is additional rather than tuning.
4. Among the three previously frozen NS representatives, take the two shortest
   complete sources. The long NS sources stay out of the actual pilot search.

For the bound current corpus this gives speech ordinals 20,3,16,42 and NS
ordinals 10,65, both profiles: 12 contexts and 20 searched resets per arm.
All resets of every selected record may change. No target or stored final
packet is truncated. The case selection uses metadata rather than a new
algorithm's quality results. The old dataset has already been examined; no
independent heldout or independent-speaker claim follows.

## Five fixed pilot arms

All arms use 64 anchors, two-frame windows, beam width 3, four spectral and two
excitation finalists, 160-sample excitation horizon, zero marginal-reclaim
control budget, at most 4096 full renders and 2 process CPU seconds per reset.
Each helper starts from the identical current baseline, not another arm's
output. Do not transfer unused CPU between resets or restart a naturally
completed call.

- **T-local-0:** unchanged old trajectory, lambda zero, local1280 screening,
  amplitude capacity policy. This is the practical current control.
- **T-full-0:** unchanged old proposal/allocation generation, lambda zero, full
  output screening. This pilot-only ablation separates screening from new moves.
- **G-full-0:** new opt-in generation, full output screening, lambda zero.
- **G-full-.1:** identical new generation with alpha .1.
- **G-full-1:** identical new generation with alpha 1.

The new generation reserves the direct previous-spectrum repeat before SSE
pruning, uses cap-aware excitation refitting derived from actual serialization,
and retains at most three cross-rate extras allocations per spectral branch.
Its allocation limit is 256 full evaluations globally within each reset helper,
at most 16 per branch, also charged to the 4096 render and CPU bounds. Old
controls keep the old generation unchanged; their existing unused allocation
parameter remains zero. Actual settings and meaningful source contracts must be
checked against the frozen opt-in API before execution.

The pilot is exactly 60 arm-records, 100 actual reset helper calls, 180 derived
cap views and 200 nominal process CPU seconds. A stopped/failed attempt is kept,
never silently restarted or omitted. Synthetic preflight is a separate finite
stage with its complete helper/cost accounting and no corpus outcomes.

## Distortion, rate and price

Primary inner D is exact full-output PCM16 SSE. R is 8 times actual complete
serialized bytes, including each 22-byte reset header, actual spectral Rice
choice, extras flag/markers/values, stored tail and independent byte padding.
It is not callback-requested bytes, parameter-only bits or a hypothetical
repeat/delta syntax. Fixed-width scale/lag/gain/base pulses do not directly
save v5 bits; changing them can compensate distortion from spectral/extras
rate changes. Every advertised cost must equal actual serialized length.

After the fresh whole baseline audit, define one shared recording-wide price
lambda = alpha * baseline_full_PCM_SSE / (8*B), passed unchanged to every reset
helper. Full-output screening makes the D scale agree with final ranking.
If baseline SSE is zero, lambda is zero for every alpha; label the degenerate
case rather than inventing a data-dependent floor. Alpha values, CPU bounds,
move limits and selection policy are not tuned after pilot results.

Run once at each arm's common whole ceiling B, with local cap min(B,65535).
Derive B, floor(.95B) and floor(.90B) decisions from those saved new candidates;
there are no per-cap fits or searches. Preserve zero-price incumbents and all
actual-byte/distortion nondominated alternatives: finite beam/price response
need not be monotonic and a lambda winner is not a global optimum.

## Whole selection and quality

Capture actual serialized endpoints and objective scores. Apply the same
deterministic at-most-16 local SSE/byte frontier policy to all arms, separately
retaining baseline and returned selected/raw endpoints. Independently verify
the serialized model SSE used for pruning; count this raw-pool audit separately.
The first pilot uses at most five fresh whole views per arm-record: baseline,
concat selected, concat raw, common minimum-byte and common minimum-SSE local
frontier views. No Cartesian product, per-reset depth mixture, global DP or
post-outcome endpoint selection is introduced. Retain all labels on exact
ordered-byte deduplication. Intermediate frontier points remain evidence,
not silently claimed whole-admitted outputs.

Fresh whole PCM/PWM SSE/STOI, period coverage, clipping and voice/noise/joint
metrics use the same complete target and current baseline. All canonical
whole gates must pass; smaller fitting amplitude seeds or raw outputs are not
weaker admission anchors. Rank eligible output by joint score/actual bytes/ID
at each fixed cap. Additionally publish minimum actual bytes preserving all
baseline gates and the bounded size/quality frontier. Raw tradeoffs, no-fit and
no-admission are explicit negative results. Old cached metrics cannot replace
new-study measurement; exact ordered bytes+target+speech+source-context caching
within the new study is allowed only with creating-event provenance/counters.

Compare new generation0 to old full0 for the move/allocation effect, priced
new generation to new0 for the price effect, and all new modes to old local0
for the practical comparison. Every extra run is paid. The actual complete
helper CPU ratio<=1.25 remains the matched-helper comparator; quota allocation
does not imply equal spent or end-to-end CPU. Separate initialization/search,
finalization, capture persistence, raw-pool audit, bounded frontier pruning,
whole admission, cache and full workflow costs. No free prior work is included.

## Corpus extension and admission boundary

The pilot outcome is retained even if negative. Do not replace the grid,
retune alpha or weaken gates after seeing it. A separately authorized corpus
extension uses the same frozen baseline policy and four primary arms (old
local0 plus the three new modes); the pilot-only old full0 ablation is reported
separately. On all104 contexts, all118 speech resets and all124 NS resets get
a chance to change: 242 searched resets/arm, 416 arm-records, 968 helpers,
1248 cap views and 1936 nominal CPU seconds at the same2s/reset bound. Do not
reuse pilot searches as free corpus work or call overlap independent evidence.

The previous long NS worst+tail policy fixes58/60 resets. Its header-only
editable lower bounds already exceed95% of both current long B values; those
two old-policy cases are registered structural diagnostics, not algorithmic
compression failures. The eventual full-corpus policy searches all60 resets
of each long record, preserving every original reset and full target.

Numerically eligible smaller outputs still require actual linked whole-player
Flash/metadata costs, ROM versus external stored bytes and requested SPI bytes,
full IRQ-active playback and later controlled same-level listening before
adoption. No decoder/program-Flash benefit is inferred from host code or data
bytes, and no local metric result is perceptual equivalence proof.

Source identities, paths, media, all input/stream/reference/native/PCM/binding
fingerprints and detailed logs stay in ignored build storage. Public evidence
is anonymous numeric data and code/runtime provenance only. Inspect staged
content for private data, commit focused changes, and do not push.
