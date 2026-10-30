# Independent V2 saved-stream audit

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
comparisons. This smoke does not establish the full study audit; completed
aggregate receipts are saved separately after every predeclared worker finishes.

From the repository root with the pinned numerical runtime and compiler in PATH:

```text
python Codecs/LPX/research/v5-adaptive-voice-independent-audit-2026-10-30/reproduction/test_audit_saved.py
python Codecs/LPX/research/v5-adaptive-voice-independent-audit-2026-10-30/reproduction/audit_saved.py --source-root ACTIVE_V2_ROOT --study COMPLETED_PRIVATE_STUDY --output build/adaptive-audit/fresh-output
```

Outputs must be fresh and under owned ignored build storage. `--partial` permits
a read-only diagnostic of currently complete records and explicitly reports
missing records; it cannot produce a passed full-study receipt. Unexpected
failure details are written privately, while console output contains only
status and exception class. The auditor checks its own source bytes at both
boundaries so a source edit during execution cannot change the reported epoch.

Neither a numerical audit nor unchanged decoder source establishes audibility
or real-time support. Complete-player Flash/SRAM/stack/PWM/timing checks with
interrupts active remain a separate admission step. The ordinary frontier is
serialized-data-byte/score, not a complete-image Flash frontier.
