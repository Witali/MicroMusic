# Canonical whole-chain retention: saved-corpus replay

This is a predeclared regression replay of the canonical encoder-side whole-chain
selector, after the targeted prefix-retention diagnostic exposed an incumbent
loss. It is not an independent heldout quality study. It does not change the
codec, decoder, local search, source level policy, or frozen V2 evidence.

## Fixed population and inputs

Replay exactly the original completed 118 V2 jobs in binding order: 98 speech
screen, 14 paired speech default, and 6 nonspeech default records. Use their
saved candidate-sink bytes and local stage histories. No new fitting,
refinement, candidate encoding, library build, or mixture search is allowed.
The final independent 118-record PASS, all six complete worker receipts, record
markers, actual pool bytes, source references, native libraries, runtime,
original core `5a6cd1ab`, and canonical selector source must be pinned.

The screen records have 118 searched resets and 1,862 pool rows. The paired
default subset has 22 searched resets and 731 rows. Nonspeech has 124 resets,
of which only 8 were searched, with 227 rows. In each long nonspeech record,
only reset indices 35 and 59 have histories; all other 58 reset streams remain
the exact baseline. Every full source, including the partial final reset, is
retained. No segment is shortened to satisfy cost or runtime limits.

Reconstruct the declared target from the pinned original reference using the
frozen `plan_level` and `quantize_target`, verify no clipping, and require the
exact saved target PCM digest. Preserve and auto-quiet are separate declared
contexts. Full target reconstruction must precede all selection.

## Canonical call and comparisons

Call canonical `adaptive_speech_chain.select_candidates` once per record,
passing the exact whole baseline and the saved subset of reset histories.
Common stage depths range from zero through the maximum actual completed
local stage count: one for screen and four for default/nonspeech. Unsearched
resets stay at baseline. The selector retains selected and raw snapshots at
each common depth; it does not vary depths independently by reset.

Pass the original complete whole control, selected, and raw chains as
incumbents. For paired default records also pass the actual screen budget
selected/raw fallbacks at all three caps. These are known saved bytes, not
fresh local searches. Deduplicate exact ordered reset-byte tuples, retaining
all role labels; different reset boundaries remain different chains.

Use the canonical callback once for every distinct whole chain to bind actual
ordered bytes, verify row byte totals, and retain private artifact descriptors.
Canonical selection freshly measures complete target metrics, including PCM16
and fixed PWM8 SSE/STOI, clipping, period coverage, and joint voice/noise score.
Native common/v5-only and model outputs must agree for every distinct reset
stream; a cache may reuse exact reset bytes in the same decoder context.
Whole metrics are fresh per distinct ordered whole chain within each record;
there is no old whole-metric reuse. Exact known-chain whole rows must reproduce
the independently audited saved values and quality flags.

Run canonical `choose_budget` on the retained whole rows at the original
100%, 95%, and 90% complete-stream caps, without per-cap refitting. For every
cap, require the new chosen eligible result to be no worse in `(score, bytes)`
than each already known feasible eligible old result, including paired screen
fallbacks. Preserve explicit raw-only, no-fit, and no-admission outcomes.

## Contracts, attempts, and runtime

Before replay, run meaningful research-driver contracts for exact target
reconstruction, sparse reset histories, ordered-byte deduplication, saved row
binding, incumbent comparison, and old-union inventory. These supplement the
canonical module's own tests; they do not edit canonical tools/tests.
Run a read-only actual saved-row contract across all 118 records before new
replay measurement. It checks immutable markers, static eligibility/ranking,
history geometry, and target hashes with zero fitting or refinement.

Bind driver/protocol/selector sources before execution. Every actual replay
attempt writes a private started/complete/failed journal and private failure
traceback. A failed attempt remains immutable and is not overwritten or
silently resumed. Bootstrap-only failures before a replay attempt remain
separate. Process handles and terminal status are reported. Execution may be
split into two fixed source-ordinal parity shards, each retaining both
profiles, with disjoint output/log namespaces. No shard is retried without
coordination. Numeric counters distinguish whole metric work, unique reset
verification, cache hits, records, and wall time.

## Complete firmware scope

Reconstruct the old player union from all original changed automatic
selections and their exact rollback chains; require exactly 75 distinct
ordered chains. For each newly chosen result record whether it is unchanged
baseline, already in that union, or outside it. This inventory neither expands
nor invalidates the previous union proof. Any outside chain needs separate
actual complete Flash and interrupt-active playback evidence before firmware
admission. No constant program-size estimate is reported as measured Flash.

## Publication and scope limits

Keep source identities, paths, stream/reference/native/PCM/binding fingerprints,
logs, artifacts, and tracebacks in ignored private build storage. Public
projections allow anonymous ordinals, numeric profile/phase results, costs,
metric values, counters, code hashes, and source commits only. Scan the exact
staged content before each focused commit. Do not push. Numerical gains do
not establish audible improvement, and replaying the same data does not make
it independent evidence.
