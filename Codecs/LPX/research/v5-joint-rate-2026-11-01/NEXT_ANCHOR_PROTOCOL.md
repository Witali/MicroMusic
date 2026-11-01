# Proposal only: useful-anchor ordering experiment

This is a proposed separate tuning experiment, not permission to execute, a
change to the completed five-arm pilot, or a full-corpus extension. Integration
owns the ordering implementation and must freeze the final API, exact rules,
source epoch, contracts and a new experiment package before any new outcomes.
The motivating observation is already known: every pilot helper first started
anchor 0, and new generation completed far fewer parent expansions than full
control. Therefore this is not an independent heldout evaluation.

## Baseline and finite scope

Reuse the exact pre-pilot strongest canonical plus target-admitted matched-CPU
baseline binding and its 12 selected complete contexts. Preserve the same target
bytes, source level, reset geometry, full stored tails and B. In particular the
NS profile4 baseline remains 635 bytes: the pilot's unadopted 634/633-byte outputs
do not replace it. Pilot winners remain archived comparisons; do not insert them
as free search seeds or whole-candidate incumbents that could mask ordering.

Keep speech ordinals 3, 16, 20 and 42 and short NS ordinals 10 and 65, both
profiles. All 20 reset contexts remain editable. Four arms mean 48 arm records,
80 newly paid helpers, 144 derived cap views and 160 nominal process CPU seconds.
There is no lambda grid, per-cap refit, early outcome-based stop, long-record
truncation, omitted reset, restart or full-corpus expansion.

Before each context's first search, freshly verify the full current baseline
with model/common/v5 PCM/PWM and all whole metrics at the new bound source epoch.
Old cached metric values are agreement checks, not fresh measurement. Reuse old
native binaries only through the same exact source/dependency/binary bridge;
report old and new epochs separately. New-study exact ordered-chain caching may
share fresh measurements across these four arms with explicit provenance.

## Four lambda-zero arms

Use full-output screening and lambda 0 in every arm:

| Arm | Generation | Visit order |
|---|---|---|
| T-time-0 | unchanged old generation | current ascending selected anchors |
| T-priority-0 | same old generation | useful-anchor priority |
| G-time-0 | current opt-in new generation | current ascending selected anchors |
| G-priority-0 | same new generation | useful-anchor priority |

Preserve 64 anchors, two-frame windows, beam 3, spectral 4, excitation 2,
160-sample excitation horizon, 4096 full renders and 2 process CPU seconds per
reset. Old arms keep allocation 0; new arms keep global 256, at most 16 per
branch and three returned cross-rate points. Local cap remains min(B,65535),
not each old reset's individual size. Run each arm once at B and derive
100/95/90 caps from the same saved pool without another search.

The primary comparisons are ordering within old generation and within new
generation. Compare generation under temporal order and under priority order
as additional practical comparisons. The new-generation priority rule may use
rate opportunity as well as SSE; therefore this does not isolate one universal
sorting key or a pure topology effect across generations.

## Recommended fixed ordering rule for integration to finalize

Within a generation, compute exactly the same nominated anchor set from the
identical initial baseline for both visit-order arms. Freeze that set once;
do not nominate more frames or adapt priorities after partial outcomes.

- Old priority: sort its existing set by descending baseline full 320-sample
  block PCM SSE, with frame index as the deterministic tie break.
- New priority: restrict both queues to its existing nominated set. The rate
  queue sorts positive exact two-spectrum serialized coding-bit savings from
  replacing a frame by its previous spectrum, descending, then frame index.
  The error queue sorts baseline block SSE descending, then frame index.
  Alternate rate then error, removing duplicates while retaining first visit;
  append any remaining nominated anchors in error order. If no positive rate
  opportunity exists, use error order. Temporal control sorts the same set by
  frame index.

This deliberately tests reaching a repeat-capable anchor early. The rule uses
the existing proposal's exact adjacent-spectrum accounting; its nomination
priority is not an acceptance score, perceptual metric or byte-saving claim.
Both axes still evaluate actual full serialized output. Priority calculation
and prefix-state advancement are paid inside the same cooperative quota.

Integration may choose a different fixed rule before source freeze. Record that
choice explicitly in the new protocol; do not try several order rules on the
pilot and retain a winner without reporting and paying for all such experiments.

## Required counters and contracts

Report the exact planned anchor set/order privately and its source-bound recipe.
Measure started/completed anchor IDs, distinct nonzero anchors reached, repeat
opportunities/proposals completed, refit calls started/completed, joint candidates
completed, cross-rate calls started/completed and serialized endpoints published
before interruption. Keep render/CPU/atomic-overshoot and complete helper timing.
Do not relabel inner excitation trials as refit invocations. Apply identical
cheap instrumentation in both order modes and charge it inside the quota.

Contracts should prove equal nominated sets for both orders, deterministic ties
and deduplication, fixed-order exhaustion without repeated anchors, quota stops
before the next atomic chunk, and retention of every completed candidate on an
interruption. Budget-disabled temporal mode must preserve the old bytes/numeric
reports except documented additive counters. Priority is an intentional behavior
change; no byte equality with the temporal result is expected. CPU-limited runs
must not be repeated to obtain a preferred trajectory.

Use a fixed synthetic preflight of four arms times both profiles (eight helpers)
and four warm helpers in each profile worker (eight more), separate from the
80 corpus calls. Use the existing complete 5120-sample deterministic fixture,
one anchor, window 2, beam 1, spectral/excitation 1 and 32 renders without a CPU
cutoff. Freeze source/modules and forbidden-fit/build guards before launch.

## Whole quality, costs and decision boundary

Keep the same symmetric five whole recipes per arm: baseline, concatenated
selected/raw, minimum-byte local frontier and minimum-SSE local frontier. Use
the same actual-byte/SSE bounded local frontier, exact tuple deduplication and
fresh common whole quality gates. Preserve both temporal-arm pools as paid
comparisons; do not retroactively seed priority searches from them.

Primary mechanism outcomes are branch reach and actual helper CPU. Quality and
actual bytes must be reported alongside them: reaching more anchors alone is
not a quality gain. Require actual complete-helper CPU ratio <= 1.25 for the
matched-helper subgroup; report all unmatched pairs too. Separate startup,
warmup, source setup/search, finalization, raw-pool audit, endpoint persistence,
whole admission/cache and full workflow. Equal quota is not equal end-to-end CPU.

No admission floor is relaxed. In the completed pilot every fitting speech
95/90 raw choice failed both SSE, both STOI, both period-coverage and the joint
floor, not SSE alone. Ordering must improve the candidate under those same
gates; it cannot turn that rejected result into an audible-equivalence claim.
Any smaller or numerically better output still needs a separately authorized
finite whole-player cost/playback plan and controlled same-level listening.
