# Local follow-up campaign controller

`campaign.py` coordinates the registered pitch, spectral and beam operators in
that order, repeating the sequence when required. It does not publish, merge,
change the active encoder or treat infrastructure work as a quality round.
The actual stopping rule is in [ITERATION_PROTOCOL.md](ITERATION_PROTOCOL.md).

The baseline must contain **54 final PASS receipts**, not CLAIMED/RUNNING
placeholders. Source WAV PCM bindings, completed baseline candidate/metric
coherence, the once-declared auto-quiet gain, and the two real native library
identities are checked. The private library receipt is provenance; fresh
common/v5-only native comparisons in `RoundAdmission` are the numerical
authority. No speculative Windows library rebuild is performed.

## Commands and launch gate

Use the same Python runtime and dependency environment as the baseline. All
destinations must be fresh directories under this checkout's ignored `build/`.

```text
python campaign.py validate BASELINE CHECKS
python campaign.py prepare BASELINE CAMPAIGN --libraries NATIVE_RECEIPT --validation CHECKS/validation-private.json
python campaign.py authorize CAMPAIGN --confirmed-baseline-exit --baseline-worker-pids PID1 PID2 PID3 PID4
python campaign.py control CAMPAIGN
python campaign.py status CAMPAIGN
```

Root reviews the controller, validation and manifest before `authorize` and
`control`. `authorize` requires explicit confirmation that all baseline search
workers exited and checks any supplied process IDs at that time. Process IDs
are not permanent identities and are not reinterpreted after possible reuse.
This local research activation does not authorize publication.

Validation requires each registered suite to exist, discover at least one test
and exit successfully. Sources, protocols, scientific package versions and
unit evidence are pinned. Preparation reconstructs each target from the saved
round0 gain exponent once, stores its exact PCM and never replans gain in a
later round. Both budgets must share the same declared target for a clip.

`--max-rounds N` bounds one controller invocation after complete rounds; it
does not mark the campaign complete. `--retry-reviewed-failures` permits one
new attempt for a previously failed/incomplete job in that invocation. Another
failure requires review again. Partial work and its best checkpoint remain.

## Authoritative records

All paths, media, source identities, fingerprints and detailed rows below are
private and remain under ignored build storage.

- `campaign-private.json` is immutable: 27 exact targets, 54 protected initial
  streams/metrics, baseline receipt/report hashes, original source hashes,
  native libraries, source/protocol fingerprints, fixed per-budget STOI
  membership and operator order.
- Each `rounds/round-NNNN/plan-private.json` is immutable and binds 54 jobs to
  the immediately preceding complete round's selected bytes and metrics.
- Each job attempt has an immutable claim, launch/start records and either an
  immutable PASS completion receipt or an infrastructure-failure record. A
  PASS binds the manifest, plan, job, target, input and actual selected files.
- Per-job numerical output uses `RoundAdmission`'s authoritative best pointer,
  referencing immutable candidate bytes and metrics. `selected.lpx` is a
  convenience copy and is not used as recovery authority.
- Only all 54 bound final PASS receipts can create an immutable round commit
  and anonymous summary. Restart recovery rechecks the predecessor plan,
  claims, receipts and actual files, then recomputes the full summary and stop
  transition. `ledger-private.json` is a derived convenience cache.

Immutable records are fully written and fsynced before atomic publication:
non-replacing rename on Windows, exclusive hard link on POSIX. An existing
record is never replaced. OS-held controller/job
leases and four shared worker-slot leases release on process exit. Surviving
workers retain their slots after a controller restart. Numerical imports and
JIT work happen only after acquiring a slot and job lease. No more than four
numerical workers can run in this campaign. The controller itself performs
lightweight scheduling, hashing and aggregation.

The four worker slots become available only after baseline exit. Root must
also coordinate unrelated CPU work; the controller cannot reserve CPU capacity
from other projects. Source, protocol, original reference, baseline evidence,
native identity or runtime mutation stops affected work instead of mixing
revisions. Infrastructure failures cannot advance the no-clear-gain counter.

## Aggregation

Heldout speech ordinals are 4..7, 12..15, 17 and 18; tuning speech ordinals are
0..3, 8..11, 16 and 19. Music/synthetic ordinals 20..26 are negative controls.
The public tuning phrase is not an input to this corpus controller.

Each budget reports split/group results separately. PWM STOI uses its fixed
round0 valid membership; newly missing scores fail validation rather than
being dropped. Aggregate PWM SER uses summed reference and error energies,
not mean decibels. PWM source-period coverage uses the unchanged summed
`reference_period_frames` denominator; unknown reference windows are reported
separately, and unsupported decoded/source periods are not silently removed.
PCM coverage is also reported. These are the original diagnostic scopes, not
a claim that every window's pitch or subjective quality is preserved.

Any qualifying heldout gain at either budget resets the consecutive-no-clear
count. Smaller admitted improvements remain selected but do not reset it.
Only three actually completed consecutive no-clear rounds satisfy the stop
condition. Independent firmware timing/Flash/SRAM admission remains required
for newly selected streams before any target-support claim.

Prepared code and unit tests are not quality outcomes. The initial campaign
manifest and activation are created only after root's review and source freeze.
