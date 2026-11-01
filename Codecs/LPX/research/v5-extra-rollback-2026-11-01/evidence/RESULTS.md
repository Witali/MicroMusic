# Prospective whole-chain rollback pilot

One new P4 point passes the unchanged whole-record gates and extends the complete
prior-plus-fresh-control frontier at the same data size. The gain is small and
conditional: full firmware Flash/IRQ validation and listening remain pending.
No default, decoder or format change is adopted by this study.

The experiment used the exact original pre-pilot targets/levels for speech
ordinals 20 and 42, with one and five resets. Both arms used causal positions,
horizon 160, four common coverage stages, no CPU cutoff and the same cumulative
49*initial-eligible trial ceiling. This is a targeted follow-up to an observed
failure, not a heldout corpus result.

## New point and its limits

Ordinal 42's final rollback point stays at 16,141 actual stream bytes over all
281,632 samples/five resets. Its joint score is 0.19490365679470362. It improves
the same-budget prior best (0.19502119650030214) and dominates all three previous
context-wide size/joint frontier points. Every admissible fresh continue point
is included in that comparison; superiority only to the original input was not
the success test.

| Saved whole metric | Original input | Prior best at 16,141 B | New rollback |
| --- | ---: | ---: | ---: |
| Joint score | 0.195037041474 | 0.195021196500 | 0.194903656795 |
| PCM SER, dB | 6.155537820942 | 6.155556309356 | 6.160813338754 |
| PWM SER, dB | 6.127852968899 | 6.127866633118 | 6.132257672425 |
| PCM STOI | 0.864370160855 | 0.864370509499 | 0.864450983641 |
| PWM STOI | 0.858497814891 | 0.858504143934 | 0.858511511330 |
| PCM period-coverage windows | 180 | 180 | 181 |
| PWM period-coverage windows | 179 | 179 | 180 |
| Clipped samples | 0 | 0 | 0 |

Against the original, PCM/PWM SER rises by 0.0052755178/0.0044047035 dB and STOI by
0.0000808228/0.0000136964. Against the same-budget prior best, SER rises by
0.0052570294/0.0043910393 dB and STOI by 0.0000804741/0.0000073674; joint score
falls by 0.0001175397055985. Period coverage increases by one analysis window in
each domain and clipping stays zero. These proxy changes establish neither
audibility nor complete preservation of voice pitch/timbre. Exact saved values
and movements are in [rows.json](rows.json).

Ordinal 20's final rollback point also passes the input gates, at 1,858 B and
score 0.07912488048765311, but remains dominated by the prior union. Neither new
arm has an actual byte fit at 95% or 90%: all eight reduced-cap views are no-fit.
This pilot demonstrates no preserved-quality bitrate reduction.

## All points, prospective decisions and retention

The closed audit covers four real arm records, twelve reset-pass instances,
sixteen stage events and all twelve ordered 100/95/90 decisions. Twenty real
whole attempts form sixteen distinct context/ordered-byte tuples. No mixture,
additional depth, group revisit, per-cap refit or numerical retry was introduced.

Both rollback records reject stages 1, 2 and 3, restore the protected pulse fields
and exact consumed-prefix state, then accept stage 4. Paid group progress/trials
are retained throughout. This exercises the multi-reset rejection/rollback path
on real data. Continue preserves its uninterrupted working path; every one of
its complete common-slot tuples matches the old explicit causal checkpoint-ID
references exactly.

Of eight changed rollback points, six fail full admission, one is admitted but
dominated and one extends the prior-plus-fresh-control frontier. Failed-reason
counts overlap: six fail combined PCM/PWM SSE/STOI floors, five PCM STOI, four
PWM STOI, two PCM period coverage and one PWM period coverage. None fails PCM or
PWM SSE, clipping or the original-anchor joint-score floor. Lower full waveform
error alone therefore still does not establish quality preservation.

Every tuple was persisted before native/metric work, and every completed value
and decision before later rollback/progress. Rejected complete tuples remain in
the final cap pools. Closed output hashes and the saved-only audit confirm exact
bytes, gates, protected transitions, trial/progress retention and metric-cache
origins. The comparison includes all 40 saved admissible V1/anchor/full-pass rows
for these contexts, including nonselected/above-B points, plus every admissible
fresh continue point. The old metrics remain saved bridged evidence.

## Work and accounting

| Measured real work | Continue | Rollback |
| --- | ---: | ---: |
| Eligible / visited groups | 556 / 556 | 556 / 556 |
| Actual trials / common ceiling | 22,312 / 27,244 | 22,312 / 27,244 |
| Cumulative attempted changed groups | 259 | 258 |
| Final committed changed groups | 259 | 49 |
| Rollback calls | 0 | 18 |
| Replayed prefix samples, overlapping subset | 0 | 218,720 |
| Prefix-synthesized samples, including replay | 296,360 | 515,080 |
| Real record workflow CPU seconds | 27.90625 | 28.53125 |
| Whole verification/metrics/I/O CPU seconds, included above | 25.234375 | 25.890625 |
| Worker main CPU seconds, including warm/preparation | 33.953125 | 34.34375 |
| Individual worker main wall seconds | 78.44590 | 78.06997 |

Replayed samples are already included in prefix totals; do not add them again.
API calls were timed directly. Open per-session budget lifetime clocks include
interleaved other work and are explicitly nonadditive. Equal trial counts do not
establish a matched-CPU or speed comparison, and worker walls are not summed into
campaign elapsed time. All detailed API costs remain in [summary.json](summary.json).

The new campaign made twelve synthetic arm records/sixteen synthetic instances:
six/eight preflight plus six/eight worker warm. These contribute 48 synthetic
stage events, separate from the sixteen real events/twelve real instances.
Synthetic reference construction used three explicit model decodes per process,
not initial fits. Old studies and upstream source-validation captures remain
outside these counts. Preparation cost was 4.1370 wall / 3.265625 CPU seconds;
preflight main cost 24.9916 wall / 13.359375 CPU. The final saved-only audit cost
8.5551 wall / 7.09375 CPU and performed zero new instances, synthesis, metrics,
model decodes, native builds or target jobs.

Numerical source stayed at `806d0c49`, producer research at `e2a7f6a7`, and the
saved-only audit at `8c9f3b39`. The old/new group-function AST and LF-normalized
source span are exact, with unchanged arithmetic/packing dependencies; raw full
modules are separately pinned. The extracted state owner is explicitly a new
epoch. Fifteen pure producer/receipt/controller contracts and three saved-audit
contracts pass. Integration's separate source validation reported 430 discovered
tests: 429 pass and one optional external-observer integration skip.

Owned sessions 57537 (preflight), 78065 (continue) and 63766 (rollback) all exited
zero. Saved export completed exit zero with PASS/complete receipts. Media,
source identities/paths/fingerprints, decoded reference needs and spatial progress
remain private/ignored. A single exact candidate/original-baseline handoff is
available for separately authorized finite target preparation; no old-source
target proof or audible benefit is transferred by C/DSP identity.
