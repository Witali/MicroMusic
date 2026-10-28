# Bounded V2 adaptive voice validation

This protocol is fixed before V2 corpus outcomes. It reuses measured V1 streams
and the original full references. It does not fit a new LPC/excitation seed,
normalize an evaluation waveform, change decoder syntax, or establish a global
optimum. The user chose automatic amplification of quiet input. Accordingly,
the active speech policy is 90 original-level groups and eight declared-level
auto-quiet groups, with both profiles of each of the 49 sources retained.

## Frozen inputs and implementation

Preparation requires an explicit committed V2 core revision and exact matching
working files for all active Python tools/tests and decoder sources. Pin those
bytes, this protocol, the research driver and its contract tests, Python and
numeric package versions, compiler/runtime identity, thread settings, and two
generic common/v5-only native libraries. Assert the origins of loaded project
modules, including cached imports; a source snapshot alone cannot attest the
code actually executing.

Bind the audited V1 private binding, immutable record markers, numerical reports
and captured seed streams. Pin original reference files, canonical PCM16 bytes,
sample counts, both profile records, original byte caps, and every actual ordered
reset segment, including partial tails. Source media, identifiers, paths, media
fingerprints, native images and private bindings remain in ignored local build
storage. Public evidence uses anonymous ordinal numbers and numerical outcomes.

The targeted listening source remains marked in both profiles. It is a tuning
target, not untouched held-out evidence. The same source in two profiles, a
repeated source at a changed level, and overlapping analysis frames are not
independent speakers.

## Three finite phases

1. **Speech screen:** all 98 active-policy profile groups, with at most one
   expensive refinement call per actual reset segment. The eight quiet groups
   reuse V1's declared auto-quiet target; the other 90 keep original level.
2. **Paired default-budget subset:** all four quiet sources and the shortest,
   median and longest nonquiet speech sources, ordered by full sample count and
   source ordinal before outcomes. Retain both profiles: seven sources / 14
   groups. Use at most four expensive refinement calls per actual reset segment.
   This is a paired follow-up on a declared subset, not 14 new independent cases.
3. **Nonspeech controls:** shortest, median and longest sources in the frozen
   original 132-source / 264-group nonspeech manifest, using sample count then
   source ordinal. Retain both profiles: three sources / six groups. Refine only
   the original segment with greatest exact PCM squared error per sample
   (earliest index on a tie), and the final segment when distinct. Use at most
   four calls for each edited segment. Every other segment stays byte-identical.
   Compute no STOI for these controls. Evaluate every complete original chain,
   including the long-chain case; do not truncate to 64,000 samples.

The median is the element at index `len(ordered_sources) // 2`. The source
selection uses no V2 outcomes. There is no adaptive expansion to more cases,
extra seed grid, cap-specific search, or retry with different settings.

## Seed and anchor semantics

Call the frozen `refine_candidates` API directly. Do not call its seed-fitting
`encode` wrapper. Replace `speech_v4.encode` with a guard that raises if called;
report zero new seed fits separately from expensive refinement calls and their
internal local evaluations.

For speech, reuse all actual ordered/deduplicated V1 captured seeds. A local
anchor is V1's conservative local selected stream when present, otherwise its
first captured legacy control. Revalidate every actual seed through common and
v5-only native PCM/PWM and the independent model. Check profile, full local
sample count and declared source target. Recompute V1 baseline/trial diagnostic
claims where their source stream can be identified, rather than trusting saved
metric labels.

Use the frozen optional candidate sink to retain each distinct verified V2 pool
stream exactly once, in report-ID order. Recompute each saved row against its
actual bytes; keep lower-level screened probes separate from this measured pool.

The whole speech rollback anchor is the independently audited V1 **100% selected
chain**, after verifying its complete V1 admission. It may differ from the
concatenation of local anchors. Keep the declared-level V1 legacy chain as a
separate comparison, not another selectable chain. For nonspeech, original
streams are both the rollback and the only starting seeds. No new fitting is
needed for either cohort.

All local searches use the original **whole-source** complete-byte cap, avoiding
arbitrary proportional caps. The serialized complete chain must pass its real
whole cap again. Record the frozen LPC preset, extra-pulse settings, header
search limits, operator order, objective descriptions and all internal work
counters. A refinement-call count does not imply a wall-time limit.

## Whole-chain selection and quality domains

Retain at most three choices: whole rollback/control, concatenated returned
selected streams, and concatenated returned raw streams. If any local returned
stream is absent, the corresponding complete choice is absent. Do not search
mixtures of segment alternatives. Decode the entire ordered chain afresh using
the independent model and both native decoders, checking PCM16 and fixed 8-bit
PWM separately. Recheck original saved-output fingerprints too.

Recompute complete-target PCM/PWM SSE and available speech STOI, source-bound
voice/period diagnostics, clipped sample count, spectral/noise descriptors, and
the frozen joint objective. Use the frozen V2 admission policy: PCM/PWM metric
non-regression, no additional clipped samples, no lower number of within-tolerance
period windows in either output domain, and no larger joint objective than the
whole rollback. Finer shape/collapse measures remain visible tradeoffs unless
the frozen core explicitly makes them hard floors. A whole failure returns the
whole rollback if it fits; local successes cannot override a whole failure.

Apply the same three measured whole choices to true integer byte caps
`floor(original_bytes * percent / 100)` for 100%, 95% and 90%. Rank eligible
choices by joint objective, complete bytes and fixed role order
control/concat-selected/concat-raw. Also retain the best merely fitting raw
tradeoff and explicit null/no-fit rows. These are finite-pool feasibility
observations, not cap-specific reoptimization or proof that a better stream
cannot exist.

Report source-period-unassessed cases, vanished/aperiodic output, paired pitch
coverage, octave errors and reference PWM collapse. Missing output pitch cannot
count as preserved pitch. A skipped metric because the source/control is
unassessed must remain visible. Keep quiet declared-level quality separate
from original-level quality; never add SSE across different target levels and
describe the difference as quality improvement.

## Execution, caches and audit

Prepare once, then use deterministic source-ordinal parity shards, retaining both
profiles of each source on one worker. Freeze source/runtime/native libraries
and inputs before/after records and at worker boundaries. Log numerical progress
only. Keep private per-record artifacts immutable. Reusing a complete cache
requires its exact prepared identity, report and artifact fingerprints.

Journal every attempt before work; journal each expensive operator start and
completion. Preserve failed/incomplete attempts and their observed work counts.
Mark an attempt complete before writing the immutable completion marker, which
is the final commit point. Count actual new/refinement work, cache reuse, prior
attempts, CPU/wall scopes, internal evaluation limits and interruptions. Do not
hide unsuccessful prior work behind a resumed result.

After the frozen run, independently reopen saved streams and recompute full
selection/admission before publication. Actual player Flash/SRAM/stack/timing
admission is a separate step on the union of promising changed streams; data
bytes alone do not establish complete firmware savings or hardware support.

## Interpretation

The V1 study is a bounded first-stage control. Its original-level rollbacks
establish conservative retention, not universal voice preservation. V2 is
evaluated against those accepted measured streams. Numerical voice/noise
proxies and synthetic input checks do not prove audibility, speaker gender,
universal pitch preservation or a general improvement on music. Both targeted
user observations remain valid: the amplified new sample sounded much better
than the old encoded sample, and still sounded rougher than the original.
