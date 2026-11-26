# Whole 20-second audiobook study

Registered before audiobook encoding outcomes, 2026-11-26. The software
predecessor is `654a95c76bf3d0687b328231a637e0b5791d55e0`, including the completed
short P3 study. All earlier source files, protocols, reports, media bindings and
receipts remain historical evidence and are not relabeled by this study.

## One narrow software extension

Raise only the automatic P3 fine-grid phase's host sample limit from 64,000 to
160,000 samples: exactly 20 seconds at its existing 8,000 Hz rate. Use one named
constant for model validation and eligibility. Keep all API signatures, status
codes, selectors, guards, candidate generation, bandwidth argument .97,
normalization policy and arithmetic unchanged. No decoder or format change.

Other eligibility requirements stay fixed: level 3 / P4 syntax, calls 4, a null
prefix, zero reset state and no lookahead. Both existing quality and joint
search switches are required. `LPX_ENCODER_COMPACT_ENSEMBLE=0` retains the exact
previous encoding path. More than 160,000 samples remains outside this optional
phase; it does not become an encoder error. Previous enabled behavior through
64,000 samples must remain byte-identical.

Finish the current complete P3 operation first. Its actual complete file bytes
are B0, including the existing 17-byte Long header. The nominal accuracy budget
C is reported separately and is not extra space for the optional phase. Make
physically identical accuracy-4 copies of that finished incumbent, prove their
packed/rendered identity, and call the existing `encodeThreeK` once at B0.
Select through the unchanged production selector against the immutable finished
floor. Keep a selected fine stream at host accuracy 4 so it is not requantized.
Explicit search/validation failures record their optional status and retain the
exact successful prior output. Disabled brightness remains disabled.

Every 20-second target is one continuous encode/render/decode. Never split it
into reset 8-second files or splice separately decoded PCM. Use the existing
Long sample-count and payload fields and native `beginWideV9` entry point.
Validate model/native PCM equality, actual complete B0, all samples and EOF,
interpolated stability, level and spectral safety. This extends a host encoder
policy; it does not establish a new AVR ROM, timing or interrupt profile.

The registered efficient corpus harness composes the same operation without a
second full baseline encode. First call `encodeAccuracy` once with a fresh
nonnull reset `Stream{}` prefix whose quality target is explicitly `Pwm`. This
prefix has no continuation, history, lookahead or fitted fields; it skips only
the optional phase. Then call `refineCompactEnsemble` exactly once on that
retained complete baseline and its actual B0. This route is permitted only
after independent tests prove the reset-prefix floor identical to the null-
prefix macro-0 floor and the full automatic Long result identical to the
composition. No already measured source result informed this route.

## Tests and freeze before audiobook outcomes

Keep the pre-extension implementation bytes in ignored local storage for
paired builds. New independent tests live under `audiobook-study/tests`, leaving
the earlier short-study evidence intact. Check 64,000 / 64,001; 65,535 / 65,536;
128,001; and 160,000 / 160,001 samples. Exercise genuine Long headers, count
high bits, actual payload size, native PCM/PWM and complete EOF, odd-grid
selection, same-B0 rejection and explicit error rollback. A separate synthetic
decoder control may exceed 65,535 payload bytes; it is not a corpus or AVR
support claim.

Check all unchanged scope exclusions: prefixes, reset first-window prefixes,
continuation, other rates, profiles and call counts. Prove explicit switch-off
identity against the predecessor and enabled short-input identity. Preserve
caller-owned workspace and cleared raw-capture semantics; add no allocation
reset, exception handling or timer hooks to the production library. Freeze
software, build inputs/options, independent test receipts and source inventory
before any audiobook encode result is inspected.

## Source-only fixed cohort

Root prepares 20 fixed fragments from the user's local audiobook collection.
The ignored manifest binds original bytes, decoder/resampler versions, source
groups, exact offsets, prepared integer PCM, duration and hashes before any
encoding. Each prepared target has exactly 160,000 mono PCM16 samples at 8 kHz.
The fixed source interval is 120..140 seconds, frozen from source metadata
before encoder outcomes.
Preserve declared source level: no fitted gain, normalization, silence trimming,
time alignment, repeated padding or outcome-driven replacement.

Freeze 12 development and 8 held-out fragments by source group. Fragments from
the same recording/book group must not cross the split. Record the source-only
grouping and any limitation on book/narrator independence before outcomes;
absence of a previous manifest hit is not proof of project-wide novelty.
Do not change membership, offsets, duration or split after seeing quality.

The primary first pass uses ONE `QualityTarget::Pwm` encoding target per
fragment, protecting both native PCM and mapped PWM paths. This is 20 streams,
not separate PCM-only and PWM searches or 40 full encodes. A PCM-only policy
comparison is explicitly deferred; if later requested, it needs a prospective
extension and its own finished baselines. Both active paths are measured here.

Source identities, paths, source/audio/stream fingerprints, audio, model data
and complete journals stay ignored. Retained reports contain anonymous
ordinals, split/group counts, numerical evidence and software provenance only.
No source audio or spoken content is uploaded, committed or published.

## Run and report

After source and test freezes, run one registered development infrastructure
pilot, audit its immutable evidence, then all 20 fixed targets. A verified pilot
may be reused in the matrix and is not another independent case. No criterion,
loss, bandwidth, neighbor or refit sweep is authorized by this protocol.

Use otherwise identical predecessor/extension builds and complete targets.
Paired predecessor, explicit switch-off and automatic/composed builds establish
the mechanism and compatibility gates. The primary corpus uses the validated
composition above in one current build, not a second full speech encode merely
to reconstruct the same floor. Retain the full host model; do not recover the
Long model through the older 13-byte-only research parser.
Report each baseline, returned raw candidate and selected output separately.
Actual B0 is mandatory even if nominal C would permit growth. Include final
bytes, both PCM/PWM SSE and STOI, active voice/noise/pitch/clipping, spectral and
temporal measures, raw/selected changes, odd ranks/update cadence, optional
statuses and search counts. Preserve every source in case/byte/error totals.
Freeze STOI membership from the baseline per case/path; an eligible missing
variant makes its mean unavailable with an explicit count rather than shrinking
its denominator. Keep development and held-out denominators separate.

Independently replay the saved complete Long files through the actual native
decoder and model to EOF. Hash-check all local artifacts and private/public
bindings. Report the strict research retention diagnostic separately; do not
retroactively impose it on production selection or change either guard.
If selected outputs change, posthoc band evidence must distinguish global
1-kHz band error from retention and from bin/time-local or audible quality.

Record each composed baseline/helper call's wall/CPU time and environment,
including its internal validation/capture overhead. External timers add no
production hook. These are component-composition times; a full automatic
null-prefix API call is not separately timed on the corpus, and its cached
evaluation/memory costs need not equal the composition's times. Single-run
timings and equal bytes are not controlled speed ratios or AVR cycle measurements.
Peak working memory is unmeasured unless explicitly instrumented. Native
no-exception/no-RTTI compilation is not an actual freestanding/WASM test.
