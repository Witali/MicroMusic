# P3 automatic fine-grid candidate, round 2

Registered 2026-11-26 before new speech results or production integration.
Predecessor: `a7eca3a5`, including the canonical local-scoring fix and the
completed first study. Its source, protocols, artifacts and reports stay frozen.
This arm implements a candidate policy using the EXISTING production selector.
It does not relax the conservative octave rule or the research retention rule.

## Operation and scope

Finish the complete previous `encodeAccuracy` operation first. Its packed
actual complete byte count is B0; the larger nominal policy allowance C is
not available to this extra phase. Retain that exact finished stream outside
the candidate search and selection.

Eligibility: accuracy level3, 8000 Hz, calls4, 1..64000 samples, null prefix,
reset state and ordinary P4 wire syntax. In particular, a nonnull first-window
reset prefix is ineligible, as are continuation, Long, other rates, levels and
call counts. A separate `LPX_ENCODER_COMPACT_ENSEMBLE` build switch permits the
exact old path. Run the phase only when the existing quality and joint-search
switches are also enabled. Default enablement in this experimental branch is
permitted after mechanism validation; no publication or deployment is implied.

Make two physically identical finished-incumbent copies with host accuracy4.
Prove pack/render identity before search. Call existing `encodeThreeK` exactly
once, with bandwidth .97, cap B0, and those copies as incumbent/prefix. This is
fresh bounded source-derived spectrum/excitation allocation, not an LSF-only
search. Do not add header, bandwidth, joint or gain/normalization passes.

Validate target, complete geometry, actual bytes, model/native/EOF equality,
stability, synthesis level and spectral safety before exposing a candidate.
A disabled brightness filter must stay disabled. Compare with the EXACT
finished P3 floor through unchanged `selectQualityProposals`, reusing the
immutable matching evaluation context. Keep a chosen fine stream at host
accuracy4 through final pack/render; no later P3 re-quantization is allowed.

An unchanged proposal remains unchanged. Search, malformed-result or validation
failure retains the exact finished prior output and records the optional
stage status separately; it must not invalidate or overwrite the previous
successful report. Count this phase's search/selection work independently.
Do not repurpose the preceding phase's score denominators or legacy counters.
No decoder/parser/table/format change or new assembly is allowed.

## Evidence before speech

Independent tests must cover physical relabel identity and genuine odd-rank
packets; exact rollback for errors, malformed/over-B0/native-invalid results;
and acceptance only by the existing complete selector. Exercise PCM and PWM
separately. Test explicit switch-off identity and all scope exclusions,
including calls0..3, nonnull reset/continuation prefixes, rates12000/16000,
other levels, and the64000/64001 boundary. Do not infer continuation support
from isolated reset replay. Keep prior first-study tests unchanged.

Freeze implementation, adapter, software/source fingerprints and test receipt
before the new corpus run. The disabled build must reproduce all eight stored
original development baselines exactly. Enabled/disabled full encodes then
use otherwise identical sources/options and independent final native checks.

## Source-only reserve selection and preparation

The four old public clips are development examples only. A separate source-only
audit selects the eight existing unused reserve recordings (six VCTK and two
FLEURS), without reading new encoding results. Freeze their exact source bytes,
provenance, prior-use audit and identities in an ignored local inventory before
encoding. Describe any limitation on the term heldout explicitly; no assertion
of complete project-wide novelty follows merely from an absent manifest row.

Use the existing pinned project resampler to prepare 8000 Hz integer mono,
preserving the declared source level. Use a fixed prefix of min(4 seconds,
complete resampled source), with no silence trim, alignment, gain fitting or
normalization. Fix every prepared-target digest before the pilot. All eight
sources stay in denominators, including silence or unavailable STOI. Do not
select, replace or shorten clips after seeing candidate quality.

Public retained case reports use anonymous ordinals/group numerical summaries
and software provenance only. Source identities, paths, fingerprints, audio,
model/stream payloads and full journals stay ignored. Generic dataset origin
and license references may be retained. Do not upload private inputs.

## Run and report

Use one development case only as an infrastructure pilot, then all four
development and eight reserve sources separately for PCM/PWM. Reuse an
immutable verified pilot where applicable; it is not another independent case.
No criterion or source tuning after the pilot. Report enabled raw candidate,
the selected output and each same-source disabled B0. The strict old retention
check remains a POSTHOC diagnostic, not a newly imposed production requirement.

Report actual bytes, both waveform errors/STOI, active-path noise, voice/pitch,
clipping, full-rate spectral/temporal measures, accepted/fallback counts,
spectral updates/odd ranks, and phase work/time. Report development and reserve
groups separately and inactive PWM diagnostics as inactive for PCM selection.
Any tradeoff must remain visible. Scores and one earlier unblinded preference
do not establish audible improvement on the reserve corpus.

Report single-run host timing with its environment and validation overhead;
do not treat it as a controlled hardware speed ratio. Changed streams can
change AVR work despite identical decoder code. No new ATtiny88/ATmega328P
interrupt/underrun or physical-board support claim follows from this test.
