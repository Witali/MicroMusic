# Matched data/CPU joint-search comparison

All **248 arm records, 312 corpus helper calls and 744 cap decisions are
complete**. No initial fitting, interrupted helper, failed worker or repeated
corpus call is recorded. The final read-only export reopens the saved source,
input, candidate, whole-chain and cache-provenance artifacts and passes.
Target complete-Flash and player/SPI admission was completed separately:
[ROM costs and interrupt-active playback](../v5-matched-search-player-2026-10-30/RESULTS.md),
[full-length external SPI playback](../v5-external-spi-player-2026-11-01/RESULTS.md).
The numerical export's original pending-gate receipt is retained unchanged;
the later target receipts establish that separate evidence.

Of 124 paired record/tier comparisons, **64 meet the predeclared actual total
helper-CPU ratio <=1.25**, while 60 do not. At the common 100% data ceiling,
single-path LPC has a lower final joint score in 35 matched pairs, trajectory
in 16, and 13 are numerical ties. PCM16 SSE has the same 35/16/13 split in this
matched subset. These are overlapping record/tier views of 61 unique baseline
contexts, not 64 independent sources. Lower joint score is a numerical proxy,
not a percentage of audible quality.

| Matched domain / tier | Profile | Pairs | Single-path lower score | Trajectory lower score | Equal score |
| --- | ---: | ---: | ---: | ---: | ---: |
| Speech, 2 s/reset | 4 | 29 | 19 | 5 | 5 |
| Speech, 2 s/reset | 6 | 27 | 15 | 7 | 5 |
| Speech, cumulative 2+8 | 4 | 4 | 1 | 3 | 0 |
| Speech, cumulative 2+8 | 6 | 3 | 0 | 0 | 3 |
| Nonspeech, 2 s/reset | 4 | 1 | 0 | 1 | 0 |

There are no matched profile-6 nonspeech pairs and no matched cumulative-2+8
nonspeech pairs. The selected deep speech subset is small and includes the
previously examined quiet population; it is not independent heldout evidence.
The 60 unmatched comparisons remain in the export: single-path is lower in 29,
trajectory in 14, 16 have equal score and bytes, and one has equal score with
fewer trajectory bytes. They are not counted as matched-CPU wins.

Both arms use exactly the same strongest current canonical 100% baseline,
declared source level, complete target, reset geometry and actual data ceiling
B. A ceiling is not a promise of identical output byte counts: among the 64
matched pairs, 56 have equal selected stream bytes, five have fewer single-path
bytes, and three have fewer trajectory bytes. The 8-second result retains all
same-arm 2-second whole incumbents and is explicitly charged as cumulative
2+8. Earlier work is not free.

No arm achieves an automatically admitted 95% or 90% result. At 95%, 246 views
have no fitting whole tuple and two have fitting raw tuples that fail the
quality gates. Those two views share one distinct raw tuple in the trajectory
2-second and cumulative tier. At 90%, all 248 views are no-fit. This is a negative result for
the fixed finite endpoint/search policy; it is not proof that another v5
encoding cannot reduce data by 5% or 10%. No per-cap refitting was performed.

## Measured CPU and validation work

| Work across both workers | Process CPU, s |
| --- | ---: |
| Nominal setup/search quota allocation | 984.000 |
| Actual source-clock setup/search region | 893.813 |
| Helper finalization reported by source clocks | 127.734 |
| Additional complete-call overhead | 2.125 |
| **Caller-observed complete helper total** | **1,023.672** |
| Independent every-sink serialized model-SSE audit | 684.125 |
| Deterministic bounded frontier pruning | 0.047 |
| Candidate stream persistence | 36.828 |
| Whole admission, output checks and whole artifacts | 626.391 |
| Actual complete arm workflow regions | 2,377.891 |

The shared source clock starts after input validation/unpack and before
coefficient/filter-state initialization. Complete caller CPU includes that
validation, unpacking and report/call overhead. The matched-pair rule uses the
complete caller total, including helper finalization. Of 312 calls, 281 observe
quota exhaustion and 31 complete without observing it. The sum of positive
search-region overruns is 7.188 CPU seconds; positive complete-helper overruns
sum to 132.891 seconds. Underspending in other calls explains why these sums
are not the difference between campaign totals and the nominal allocation.
Individual maximum atomic-chunk CPU was not measured.

Shared source features and exact new-study whole-metric cache hits have
creating-event provenance. Per-arm whole-workflow timing depends on cache and
execution order. It must not be presented as an intrinsic algorithm advantage
or an end-to-end same-CPU result. Independent raw-pool validation is separated
from bounded endpoint pruning and whole admission. Costs overlap by definition:
do not add the complete arm workflow to its component rows or sum cumulative
2+8 comparison costs as campaign work.

The workers validate 25,366 distinct local captured/fallback rows, performing
907,125,728 model work samples. They then verify 764 retained reset streams
against model/common/v5-only PCM16 and PWM in 3,056 native domain comparisons,
covering 35,333,837 modeled work samples. These are repeated work counts, not
unique source duration or MCU playback samples. Whole admission measures 549
fresh exact ordered-chain contexts and reuses 212 exact contexts from this new
study only. No old-study whole metrics are reused. All 104 common baselines
reproduce their saved canonical metric values, and all required baseline and
cumulative-incumbent decisions pass.

Worker 0 completes 128 arms/172 calls in 1,343.38 s wall and 1,269.17 s process
CPU. Worker 1 completes 120 arms/140 calls in 1,203.98 s wall and 1,128.95 s CPU.
The workers run in parallel; their wall times must not be added as elapsed
time. Their combined full-process CPU is 2,398.125 seconds, distinct from the
2,377.891-second arm regions and 1,023.672-second helper total. Each explicitly
records source/input/target preparation, native loading,
four synthetic warmup helpers and final guards/receipt costs. A separate
synthetic-only preflight costs 17.30 s wall/15.33 s CPU, with four warmup calls
and zero corpus calls. The original read-only baseline-manifest construction
had no dedicated timer; its cost is unknown, not zero. The export's additional
read-only reopening cost is outside the worker timing regions.

## Reproduction and separate player evidence

The protocol commits `b04b4517` and `7a22dce9` precede new corpus outcomes.
Executed harness epoch is `843fe152`; production seams and source are frozen
at `df8443cc`. Reproduction uses the explicit repository worktree
`.worktree/lpx-v5-search-cpu` as `--source-root`, with `--source-commit df8443cc`.
The origin/hash guards retain this frozen production tree; the later optional
SPI backend has a separate source context and player proof. The exact fixed
single-path expanded and trajectory settings,
max-five whole views, 16-point local frontier, unchanged sparse NS resets,
common gates and cache keys are described in [PROTOCOL.md](PROTOCOL.md).
Nine pure driver contracts and the synthetic API/native preflight pass.

Historical live handles have expired from the process-tool
registry after inactivity. Their final journals, logs ending in PASS, all
returned helper reports and final guarded receipts are complete. This report
does not invent an observed exit code for those expired handles. The final
read-only projector is observed to finish with exit 0. No recovery rerun was
needed and no completed work was repeated.

A separate independent read-only semantic/aggregate review rederives all 744
cap choices from 761 stored whole rows, checks all 312 helper settings/quota
reports and verifies all 40 cumulative arm pools and CPU sums. It reconciles
the counters and tables above without fitting, decoding, simulation or another
full projector run. This inline review creates no source-bound audit receipt.

The final manifest contains 105 distinct changed selected whole tuples across
112 cap views: 66 single-path and 46 trajectory views. Four changed tuples are
long, complete 60-reset NS chains. Their full original final packets and target
lengths are preserved. The private 104-baseline/changed-chain manifests have
been handed to the separate player/SPI task. Its completed reports above record
actual complete costs, interrupt-active output and reuse proofs. This numerical
package itself makes no new full-Flash,
real-time, analog-audio or listening admission and does not change a default
algorithm based on numerical win counts.

`rows.json`, `pairs.json`, `groups.json` and `summary.json` retain all anonymous
numeric cases, including unmatched, unchanged, raw-only and no-fit results.
Source/runtime and contract receipts exclude private paths, input identities,
stream/reference/native/PCM/binding fingerprints and media. Those artifacts
remain in ignored private build storage. `summarize_groups.py` is a descriptive
post-export projection only; it performs no new search, decoding or metrics.
