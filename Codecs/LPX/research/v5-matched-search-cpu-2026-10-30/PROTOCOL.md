# Matched data and CPU: single-path versus multi-frame joint search

This protocol is fixed before new corpus search outcomes. It compares the
existing practical algorithms under a common process-CPU allowance, source,
whole-data ceiling and final whole-record quality gates. Their internal
pruning and conservative acceptance differ; this is not an isolated test of
beam topology. No encoder default, decoder, format or MCU source changes are
part of this experiment.

## Population and common starting points

Use exactly the saved V2 speech screen population (98 profile records at
2 CPU seconds per searched reset and arm), the existing paired deep subset
(14 profile records at 8 seconds per reset and arm), and the original six
nonspeech records at both 2 and 8 seconds per searched reset and arm. Preserve
the original NS edited-reset list: worst plus tail, including indices 35 and
59 in each long 60-reset record. Unsearched resets remain exact baseline.

This is 248 arm-records, 312 actual reset helper calls and 744 derived cap
views. Nominal search CPU allowances total 984 seconds: 472 for speech at
2 seconds, 352 for paired speech at 8 seconds and 160 for the two NS tiers.
This is an allocation of process CPU, not an elapsed-time promise or a bound
on initialization overshoot, helper cleanup or outer whole-record auditing.

Choose one strongest already measured canonical 100% baseline per identical
domain/source ordinal/profile/declared-level context across the completed
screen/default retention results. Rank by joint score, actual complete stream
bytes, then fixed phase priority (default before screen). Both arms and both
tiers start from that exact ordered tuple, target and reset geometry. There
are 104 distinct contexts; 10 original phase rows would otherwise start weaker
than their paired baseline. This baseline choice reuses existing evidence and
performs no new fitting or refinement.

For each context define B as the sum of its actual baseline stream bytes.
Every searched reset uses local cap min(B,65535). Whole caps are B,
floor(.95 B) and floor(.90 B). Derive all three decisions from one search per
arm/reset/tier; do not refit at 95% or 90%. Do not shorten a source or omit a
partial final reset to meet data, CPU or device limits. A long NS baseline can
exceed MCU Flash; host numerical evaluation does not imply firmware admission.

Reconstruct the declared target with the frozen level policy and require the
exact saved target PCM digest, level descriptor and zero clipping. Bind original
V2 inputs/markers, complete canonical retention receipts, all selected baseline
bytes, native libraries, source code, runtime and this protocol before search.

## Fixed arms

The common primary full-output search objective is exact PCM16 SSE. No voice
objective, rate penalty or marginal allocation is introduced into either inner
search. Existing inner conservative PCM/PWM/STOI gates remain in place.

| Setting | Single-path joint LPC | Multi-frame trajectory |
| --- | --- | --- |
| Frame anchors | 64 | 64 |
| Spectral finalists | 4 | 4 |
| Screening horizon | 1280 | 1280, local screening |
| Excitation horizon | 160 | 160 |
| Refit | true | existing joint/refit branches |
| Passes | 2 | existing window traversal |
| Window / beam | one path | 2 frames / width 3 |
| Excitation finalists | existing coordinate search | 2 |
| Full-render safety ceiling | existing finite expanded bounds | 4096 |
| Capacity | existing fit_capacity | amplitude |
| Allocation evaluations / rate lambda | existing capacity routine / 0 | 0 / 0 |
| Objective / selection | existing SSE / conservative | None (SSE) / conservative |

These are the exact single-path expanded preset and the fixed trajectory
configuration. The helpers may naturally finish before their allowance; do
not restart them, cycle the frame list or transfer unused CPU to another reset.
Record natural exhaustion and render/frame ceilings separately from quota
exhaustion. No post-outcome setting, grid, objective or candidate-policy tuning
is permitted.

## Clock boundary, warmup and accounting

Run each worker in one single-threaded process. Both arms for a case run in
that worker, with deterministic arm order counterbalanced using only the
pre-outcome ordinal, profile and tier. Two disjoint source-parity workers may
run concurrently, keeping both profiles and both tiers together. No other
analysis executes in a worker process while its helper clock runs.

The shared cooperative budget uses process CPU, including helper initialization
and the search loop. Check the budget at safe atomic work boundaries. A chunk
already started may complete after the quota; report actual overshoot and the
largest completed chunk, rather than describing the quota as a hard deadline.
Always keep verified baseline/best encountered bytes on exhaustion. Record
local screening, full render, objective, serialization, accepted-state, sink,
cache and incomplete-work counters where the implementation supplies them.

Separately measure caller-observed total helper process CPU and wall time,
including final helper metric/native cleanup. Report helper setup/search quota
CPU, excluded finalization CPU and outer endpoint/whole-audit CPU/wall as
separate costs. Exact sink collection inside a helper counts in that helper's
CPU; disk persistence and deterministic endpoint pruning happen outside it and
are separately charged. Do not subtract profiler or sink overhead selectively.

Startup, source/input preparation, native loading and fixed synthetic JIT warmup
occur before timed corpus helpers and have explicit process CPU and wall costs.
Warm both arms and profiles using only a predeclared synthetic 5120-sample v5
fixture, without initial fitting. Use one anchor, one spectral finalist and a
small finite trajectory beam/render limit for this warmup. Warmup outcomes are
not used to choose corpus settings; report every warmup helper call and cost.

Call an arm pair matched in actual total helper CPU only when
max(total_cpu_A,total_cpu_B)/min(total_cpu_A,total_cpu_B) <= 1.25; otherwise
report it as unmatched. Report natural exhaustion independently. Equal nominal
allowances alone do not establish equal spent CPU. Do not hide mismatches in
aggregate means or select a winner from a timed subset after inspecting results.

The 8-second retained decision also retains all completed same-arm 2-second
whole incumbents. Label this outcome **cumulative 2+8**, not 8 seconds alone.
Its comparability flag uses each arm's summed actual 2-second and 8-second
helper CPU. Standalone 8-second cost can be shown separately. Campaign totals
count each of the 312 actual helper calls once; prior 2-second work is never
free or counted twice.

## Candidate capture and finite whole assembly

Persist every exact (serialized blob, full PCM16 SSE) sink callback after the
helper returns, retaining callback order, duplicates and oversize diagnostics.
No private stream fingerprint appears in public evidence. Deduplicate actual
bytes for measurement, and retain input plus returned selected/raw even if a
helper does not export them through the sink. Verify the full serialized model
SSE and geometry for every distinct captured endpoint used for pruning.

Apply the same deterministic local endpoint policy to both arms: from feasible
actual-byte/SSE nondominated candidates, keep at most 16 endpoints, ordered by
(bytes,SSE,first-capture order). Equal-cost/equal-SSE points retain the earliest
capture. If more than 16 survive, retain evenly spaced ordinal indices including
both extrema. Returned selected/raw remain separately retained regardless of
this frontier truncation. Do not invoke fresh local voice/noise searches or
use post-outcome hand selection.

Assemble at most five new complete views for each arm-record: baseline,
concatenated helper-selected, concatenated helper-raw, common minimum-byte
frontier endpoint and common minimum-SSE frontier endpoint. Each searched reset
uses the corresponding endpoint; unsearched resets keep baseline. An absent
selected/raw view makes that complete view absent. No independent per-reset
depth combination, Cartesian product, global DP or per-cap search is allowed.
Deduplicate exact ordered reset-byte tuples while preserving all labels.
For cumulative 2+8 add the already completed same-arm 2-second whole pool as
incumbents without recomputation or fitting.

This policy bounds fresh assembly to five views per arm-record before exact
deduplication. The eight long NS arm-records have at most 40 new whole views,
not a product of their reset pools. Their full source still enters every whole
metric. Candidate capture and endpoint/pruning counts remain visible so the
restricted whole assembly is not described as a global optimum.

## Common final gates and new-study cache

Decode every distinct used reset stream with model, common native and v5-only
native PCM16/PWM and require exact equality. Full concatenated native/model
output must cover all source samples in order. Freshly measure whole PCM/PWM
SSE/STOI, clipping, within-100-cent period coverage, voice/noise components and
the joint objective. Apply the same canonical whole gates against the common
current 100% baseline. Check its fresh metric values against saved canonical
values; do not compare old eligibility flags anchored to another old control.

Within this new study only, a whole-metric cache may share a result for the
exact ordered serialized bytes plus exact target, speech flag and metric/source
context. Pin and count every cache provenance and hit explicitly. A PCM-only
cache key is insufficient. Source features and verified reset outputs may also
be shared under exact source/decoder keys. Never reuse old-study whole metrics
as newly measured evidence. Distinguish unique physical/model work, repeated
whole views, reused new-study metrics, target features and audit time.

Select at each data cap by (joint score,actual whole bytes,stable candidate ID)
among full-gate-eligible whole rows. Preserve raw-only, no-fit and no-admission
outcomes. Baseline retention must prevent a 100% regression; cumulative 2+8
must never lose a previously feasible eligible same-arm 2-second incumbent.

## Execution, evidence and limitations

Before corpus execution, pass pure clock, candidate/frontier, ordered-chain,
target, sparse-reset, cumulative-cost, cache-key and no-fit contracts plus
synthetic live API/native tests and a read-only actual baseline binding check.
Bind stable committed production seams and harness/protocol sources before the
first algorithm outcome. Write a private started journal for every real helper
attempt and save its report immediately after return, before postprocessing.
Preserve failures, started-call counts and private tracebacks; do not auto-retry
or silently reuse a partial failed arm. Source/input guards must pass again
before marking an arm or worker complete.

Public evidence contains anonymous ordinals, costs, metric results, source-code
provenance and honest CPU/wall/counter accounting only. Source identities,
paths, stream/reference/native/PCM/binding fingerprints, logs and audio remain
in ignored private build storage. Inspect staged content before focused
commits; do not push.

Report paired results by domain, profile, tier and actual CPU comparability,
including negatives and naturally exhausted cases. Numerical gains do not
establish audible improvement, unbiased heldout performance or complete Flash
savings. Newly selected streams require separate actual complete-player costs,
interrupt-active playback and listening evidence before adoption. This study
does not expand or rewrite previous frozen evidence.
