# Canonical retention: full saved-corpus regression

All **118 records and 354 original cap views pass** with canonical selector
`976c50c8`. No new fitting or refinement occurs. The replay uses the same
declared source levels, full references, saved local pools, native libraries,
runtime and complete-stream caps as the final audited V2 study. The protocol
was committed as `984be359` before these replay outcomes.

There are eight changed selection views, representing five distinct selected
chains. Three quiet profile-4 chains appear in both screen and paired-default
95% views. An existing profile-6 screen winner is restored in deeper default
search. A long nonspeech whole chain improves numerically at unchanged data
size. All other original selection bytes remain unchanged; no incumbent is
lost at any cap. These are same-corpus regression results, not independent
heldout or listening evidence.

| Anonymous source / profile | Phase and cap | Old → retained stream bytes | Old → retained joint score |
| --- | --- | ---: | ---: |
| 16 / 4 | screen + default, 95% | 3,361 → 3,365 | 0.320660 → 0.268366 |
| 18 / 4 | screen + default, 95% | 3,328 → 3,330 | 1.704493 → 0.436305 |
| 36 / 4 | screen + default, 95% | 1,696 → 1,697 | 0.226100 → 0.174285 |
| 42 / 6 | default, 100% | 23,259 → 23,259 | 0.136133208 → 0.136129593 |
| 7 / 4, nonspeech | default, 100% | 202,600 → 202,600 | 0.391031298 → 0.390610362 |

The three quiet 95% choices stay within their original whole-stream ceilings
and pass every PCM/PWM SSE/STOI, clipping, period-coverage and joint-score
floor. Their data costs grow by 1..4 B relative to the previously selected
smaller chains. Data bytes are not complete firmware costs.

The restored source-42/profile-6 chain is already in the fixed 75-chain player
union. Four distinct newly selected chains, across seven cap views, need
separate player evidence: the three short quiet chains and the long nonspeech
chain. The latter's 202,600 B data alone exceed the target's 32,768 B Flash;
the replay preserves all 60 resets and makes no device-fit claim. The old
75-chain/150-image proof remains unchanged. This package makes no new complete
Flash, real-time playback, physical-board, analog-audio or perceptual admission.

## Actual measured work

Two fixed source-parity workers completed successfully, with both profiles
kept together. Shard 0 covered 62 records and 163 whole-chain measurements in
214.92 s; shard 1 covered 56 records and 118 whole-chain measurements in 432.14 s. These
timed regions ran in parallel and must not be added as elapsed time. Both
actual attempts finished with exit 0 and final source/input guards intact;
there were no failed attempts, retries or bootstrap failures.

Across the two shards, all **281 whole-chain rows receive fresh complete
metrics**, with exact ordered-byte deduplication within each record; no old
whole-metric rows are reused. Reset-byte caches make 449 stream verifications
within their respective record contexts, covering 22,414,920 modeled work samples,
against common and v5-only native PCM/PWM output in 1,796 domain comparisons.
The sample count measures repeated work across candidates and records, not
unique source duration. Fresh results reproduce 396 previously audited whole
row views, including overlaps and duplicate roles.

The initial read-only contract binds all 2,820 saved local pool rows, 148
searched resets and 8,774,314 actual pool bytes. It reconstructs the exact
target for all 118 records, including 16 auto-quiet phase records, checks 386
static prefix ranks and 44 paired local prefix1 byte comparisons, and
reconstructs the exact prior 75-chain player handoff. This contract performs
zero model/native/whole-metric work and takes 44.08 s.

A separate post-replay byte assertion independently reconstructs every
prefix from the saved static rankings, rather than trusting the canonical
incumbent list. All 592 canonical prefix labels and 390 incumbent labels map
to their exact expected ordered tuples. All 28 paired default-prefix1
selected/raw whole tuples equal the actual screen concatenations. All 1,160
unsearched-reset comparisons preserve baseline bytes in sparse nonspeech
histories. This assertion performs zero model, native, metric or search calls.

`results.json` and `summary.json` contain anonymous numeric projections.
`contracts.json`, `source-runtime.json` and `artifact-check.json` record the
contract, executed source and artifact scope. Private build receipts retain
source identities, paths, ordered streams, fingerprints, exact bindings and
process journals; none are included in these public projections. The
postcheck helper was added after both terminal replay workers, without
changing any executed replay, canonical, frozen core or old research source.
