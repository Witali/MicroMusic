# Independent audit of frozen quiet-voice V1 saved outputs

Both independent read-only audits pass. The numerical audit recomputes all
106 source/profile/mode groups and 318 complete-chain cap choices from actual
saved streams. It calls no study-driver `chain_entry`, `verify_chain` or
`choose_budget` helper, and performs no fits, re-encoding or target measurement.
The source epoch is `5b4800f7`; production decoder bytes remain `5c7e0592`.

The audited study has 49 original references, 98 preserve-level groups and 118
original reset segments, plus eight separately declared amplified-target groups
on four whole, single-reset quiet sources. Exactly 354 preserve and 32 auto
fresh V4 fits appear in 106 complete attempt receipts; no prior, hidden or
unexpected attempt/job/worker receipt is present. Both profiles of the single
targeted source remain marked as targeted, not independent held-out evidence.

The primary audit verifies 499 unique actual streams, 1,996 native output-domain
comparisons and 22,370,368 unique modeled samples. It strictly parses every
stored packet/tail, checks common and compact-only native PCM16/PWM against the
model, verifies original complete PCM/PWM fingerprints, and recomputes local
trial updates and whole-chain SSE/STOI, PCM/PWM voice diagnostics, objective
scores/components, all floor flags, exact byte caps and priority decisions.
Actual reset geometry, original/reference levels and declared gains are bound.

At preserve level, all 98 full-cap selections are original controls; **zero
changed chains** are automatically selected at any cap. At 95%/90%, there are
zero automatic preserve selections and 22/6 raw fitting tradeoffs. Separately,
auto-declared-target selections number 8/4/0 at 100%/95%/90%. They all differ
from original-level controls; only one targeted profile's selected chain
differs from its fresh declared-target legacy control. The changed-level
results are not unchanged-level quality or audibility gains.

Known baseline metrics followed by null/nonfinite candidate values fail the
corresponding gate. An unassessed baseline leaves that constraint unset under
the frozen rule and is counted separately, not reported as pitch success.
Control self-eligibility means rollback. Six preserve chain-role views have
unassessed source pitch in each PCM/PWM diagnostic domain; these are views,
not six independent sources. No whole-chain STOI value is unassessed here.

`audit.json` records separate mode/cap/targeted counts, including all selections
versus changes from original and declared controls. `context-audit.json` checks
the prepared Python/packages/compiler/thread environment, every source's two
matching profiles, the four auto sources, and the complete on-disk job/attempt
inventory. The numerical audit took 216.20 s. Neither receipt activates an
amplification policy or makes a final-quality claim. Later operational choices
belong in separate records.

The exact executed sources are retained in `reproduction/`; their SHA256 values
match the receipts. The public context receipt normalizes Windows line endings;
its JSON values and auditor source hash remain unchanged. Only metric, pitch, objective and decoder primitives are
reused from the supplied current source root. Saved-input paths, identities,
media/PCM/image fingerprints, libraries and logs remain in ignored receipts.
This audit precedes a separate deduplicated complete-player admission stage.

For a later authorized reproduction, use the frozen source epoch and package
versions from the study binding, Python 3.12, and its already completed private
study directory. Run from the repository root; outputs must remain in ignored
build storage:

```sh
python Codecs/LPX/research/quiet-voice-v1-independent-audit-2026-10-28/reproduction/audit_corpus.py \
  --source-root "$LPX_V1_SOURCE_ROOT" --study "$LPX_COMPLETED_V1_STUDY" \
  --output build/quiet-voice-independent-audit
python Codecs/LPX/research/quiet-voice-v1-independent-audit-2026-10-28/reproduction/audit_context.py \
  --source-root "$LPX_V1_SOURCE_ROOT" --study "$LPX_COMPLETED_V1_STUDY" \
  --output build/quiet-voice-independent-audit/context-audit.json
```

Both worker receipts must already be complete. Do not use Python optimization
flags: source-bound audit assertions must remain enabled. The full V1 core,
driver, protocol and tests remain unchanged.
