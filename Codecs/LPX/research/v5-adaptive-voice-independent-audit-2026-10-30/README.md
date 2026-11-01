# Independent V2 saved-stream audit

The complete resumed study passes this read-only audit: **118/118 records and
all six final workers**, with no missing records or prior incomplete attempts.
All 238 observed helper calls completed: 118 screen, 88 default-budget speech
and 32 nonspeech calls. No fresh seed fitting was performed. The audit verifies
2,820 local pool rows across 148 local searches, 2,596 unique actual streams,
10,384 native output-domain comparisons and 119,056,937 unique modeled samples.

At the original complete-byte ceilings, the 98-group screen changes 27 complete chains
relative to its accepted V1 rollbacks; the paired default subset changes 10/14,
and the bounded nonspeech controls change 4/6. These are measured proxy-gated
choices, not listening improvements. Deeper search also exposes one whole-chain
regression relative to the one-call result, documented below.

Receipts: [audit](audit.json), [anonymous groups](groups.json),
[historical splits](split-summary.json), [paired effort comparison](paired-default-vs-screen.json),
and [source/runtime provenance](source-runtime.json).

| Phase / declared level | Groups | 100% admitted / changed vs rollback | 95% admitted / changed | 90% admitted |
|---|---:|---:|---:|---:|
| Screen, original level | 90 | 90 / 20 | 0 / 0 | 0 |
| Screen, auto-quiet target | 8 | 8 / 7 | 4 / 0 | 0 |
| Default subset, original level | 6 | 6 / 2 | 0 / 0 | 0 |
| Default subset, auto-quiet target | 8 | 8 / 8 | 4 / 1 | 0 |
| Nonspeech controls, original level | 6 | 6 / 4 | 0 / 0 | 0 |

An admitted unchanged control is rollback, not evidence of improved coding.
At tighter ceilings some raw choices fit but fail automatic floors; other pools
have no fit. Neither outcome proves that another search could not meet the cap.
No SSE is added across original-level and amplified-target groups.

The original screen split labels are tuning 40, evaluation 40 and additional 18
groups. **The two targeted groups are in the historical evaluation split** and
must not be counted as untouched held-out evidence. The paired default subset
has tuning 4, evaluation 6 and additional 4 groups, including those same two
targeted groups. Historical split names alone do not establish independent
speakers or an unused test set; targeted flags and repeated-source overlap are
retained explicitly.

## Same 14 groups: four calls versus one

At 100%, both budgets admit all 14 paired groups. Four-call search has a lower
joint objective in ten, an equal objective in three and a higher objective in
one. At 95%, both admit four groups: the deeper search is lower in one and equal
in three. Neither admits any at 90%. Every pair has the same source, profile,
prepared level, whole rollback and actual complete-byte ceiling.

The counterexample is source ordinal 42 / profile 6 at 100%: one call per reset
keeps a changed 23,259-byte whole chain with objective 0.1361295932218511.
Four calls per reset return the 23,259-byte old control at 0.13613320806467044.
This is a small numerical loss, with no audibility claim. Later local winners
consume too many bytes when concatenated, and the three-chain whole pool does
not retain the earlier feasible combination. Thus more local effort is not a
guarantee of a better whole-record choice under this protocol.

Both profiles of this five-reset source expose the allocation limitation:
profile 4 has a 16,142-byte cap but its final selected concatenation is 19,669
bytes; profile 6 has a 23,259-byte cap versus 25,980 bytes. All five local
selections change in each profile, but the complete default search correctly
rolls back. These local changes are not adopted whole-chain improvements.
Reusing saved Pareto pools for global allocation and retaining earlier feasible
whole choices is a pending experiment, not part of this frozen study.

Actual helper timing/work over the same 14 groups:

| Effort | Observed helper calls | Helper wall / CPU seconds | Complete workflow wall / CPU seconds |
|---|---:|---:|---:|
| One call per reset | 22 | 35.530 / 32.063 | 703.416 / 631.828 |
| Four calls per reset | 88 | 570.121 / 539.281 | 1,685.009 / 1,578.125 |

These are sums of journaled group intervals, not parallel campaign elapsed
time or universal speed ratios. Per-operator local/full evaluation counters,
accepted changes and timings remain in the paired JSON. Nonhelper workflow wall
sums are 667.885 and 1,114.888 seconds. They include controller scoring, V1/seed
rechecks, independent pool validation, whole native/metric checks and I/O;
audit-only overhead was not separately instrumented and cannot be inferred by
calling the whole difference audit time. This separate read-only audit took
1,785.738 seconds including overlapped generation/waits, not pure codec CPU.

User listening of the targeted 1,710-byte A and 2,060-byte B was inconclusive
("hard to say"). The larger stream remains unadopted on perceptual grounds.

This package reopens actual immutable V2 output streams and independently
reconstructs their admission and selection. It does not import the study driver
or call its selection, validation, encoder or refinement APIs. Decoder/model,
voice features, harmonic/noise features and numerical metric primitives are
shared; this is an independent selection audit, not a second perceptual model.

The frozen study scope is the [V2 protocol](../v5-adaptive-voice-2026-10-28/PROTOCOL.md):
98 active-policy speech groups at one refinement call per reset, a predeclared
paired 14-group subset at the four-call default, and six nonspeech control
groups with bounded edited resets and complete-chain evaluation. Source and
target levels remain separate. The default subset overlaps the screen and is
not additional independent material. The listening target remains marked.

The auditor checks:

- The prepared binding identity, explicit committed core, current source files,
  research sources, primitive import origins, Python/packages/compiler/thread
  runtime, pinned inputs and generic native libraries.
- Original full references, actual ordered reset streams, complete sample/byte
  counts and original PCM/PWM fingerprints.
- Every saved candidate-sink stream against the independent model and both
  common/v5-only native PCM16/PWM outputs, with content-keyed reuse reported as
  reuse rather than additional distinct verification.
- Source-bound pool metrics and harmonic/noise descriptions, hard floors,
  byte caps, selected/raw rank, data-byte frontier, seed/anchor provenance and
  stage output references. Unknown source pitch is never counted as success;
  disappeared output cannot bypass a known period-coverage floor.
- The old V1 whole-chain admission and 100/95/90 choices from actual bytes,
  the V2 whole rollback identity, concatenated returned selected/raw choices,
  complete source-level metrics and all V2 whole budget decisions.
- Actual attempt/operator journals, failed prior attempts, zero fresh seed
  fitting, six final worker receipts and their exact authoritative records.

All media, original identifiers, input/output/native fingerprints, paths and
exception tracebacks stay in ignored build output. Public projection files use
anonymous source ordinals, numerical outcomes and separate declared-level views.
The projection distinguishes an admitted rollback from a changed stream; a
rollback is not evidence that the new search improved quality. It also keeps
the inconclusive target A/B listening result separate from objective rankings.

Eight synthetic auditor contracts pass, including forbidden search calls,
vanished pitch, unavailable intelligibility, clipped output, joint-score floors,
exact whole-byte ceilings, duplicate chain identities and paired source scope.
A first complete V2 screen record passed a read-only native integration smoke:
seven unique streams, 448,000 modeled samples and 28 native output-domain
comparisons. The complete later receipt above, rather than that smoke, establishes
the reported whole-study numerical audit.

From the repository root with the pinned numerical runtime and compiler in PATH:

```text
python Codecs/LPX/research/v5-adaptive-voice-independent-audit-2026-10-30/reproduction/test_audit_saved.py
python Codecs/LPX/research/v5-adaptive-voice-independent-audit-2026-10-30/reproduction/audit_saved.py --source-root ACTIVE_V2_ROOT --study COMPLETED_PRIVATE_STUDY --output build/adaptive-audit/fresh-output
python Codecs/LPX/research/v5-adaptive-voice-independent-audit-2026-10-30/reproduction/export_receipts.py --audit COMPLETED_PRIVATE_AUDIT --study COMPLETED_PRIVATE_STUDY
```

Outputs must be fresh and under owned ignored build storage. `--partial` permits
a read-only diagnostic of currently complete records and explicitly reports
missing records; it cannot produce a passed full-study receipt. Unexpected
failure details are written privately, while console output contains only
status and exception class. The auditor checks its own source bytes at both
boundaries so a source edit during execution cannot change the reported epoch.

`--watch-seconds N` instead audits immutable records once as they finish, retaining
read-only decoding/feature caches. It waits at most 30 seconds between checks
and stops waiting at the declared deadline. A running record audit may finish
after that deadline. PASS still requires every prepared record and all six final
worker receipts; expiration produces an explicit partial receipt. This mode
does not start, restart or modify any study worker.

Neither a numerical audit nor unchanged decoder source establishes audibility
or real-time support. Complete-player Flash/SRAM/stack/PWM/timing checks with
interrupts active remain a separate admission step. The ordinary frontier is
serialized-data-byte/score, not a complete-image Flash frontier.
