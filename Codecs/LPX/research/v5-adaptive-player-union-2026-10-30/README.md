# Audited adaptive selection union: preparation

The finite preliminary scope is **75 distinct ordered chains / 150 logical
normal/+100 IRQ rows**, covering 42 changed automatic cap selections. It contains
41 distinct selected chains and 34 distinct declared-level rollbacks. Exact
byte deduplication merges overlapping phase/cap views while retaining all
comparison contexts. The maximum complete playback workload is 6,924,372
samples. The largest included chain has five reset segments.

The observed snapshot covers all 118 complete producer records and six worker
receipts. Of 354 cap views, 84 unchanged selections and 228 views without an
automatic selection require no candidate playback. The four changed nonspeech
views are retained; the long 60-reset nonspeech selections are unchanged and
therefore are not added to this union. No currently included chain exceeds the
device's Flash with stream data alone, but complete linking can still fail.

`scope-estimate.json` is an immutable **pre-audit estimate**, not permission to
run images. It was produced with zero builds, simulations or fits. The final
preparation must independently verify actual 118-record audit PASS, all six
terminal workers, exact input/output identities and the same accepted scope.
The [finite protocol](PROTOCOL.md) fixes the population, comparisons and gates.
Playback/cost evidence does not adopt a larger stream; the user's A/B target
listening comparison remained inconclusive.

## Dispatcher and source binding

`reproduction/prepare_union.py` verifies actual stored bytes, reset geometry and
completion markers. It excludes unchanged and ineligible raw tradeoffs. With
`--final`, it also binds independent audit receipts and source, checks every
audited whole decision against the current record/worker rows, and pins the
existing player preparation, source inventory, native libraries and prior image
evidence. A preliminary manifest has a different schema and cannot run images.

`reproduction/measure_union.py` supports two deterministic zero-based chain
parity shards, keeping both IRQ loads together. Each chain/IRQ has an isolated
output directory; observer, source, toolchain and prior evidence stay read only.
Rows and attempt journals are per shard. Existing attempts require explicit
inspection rather than an automatic restart. Aggregation requires both terminal
shards and reopens exact images/output proofs before producing anonymous results.

The dispatcher reuses the unchanged generic `admit.py` and `PlayerEvidence`
from `../v5-adaptive-target-player-2026-10-30/reproduction/`. Their actual loaded
paths and source digests are pinned in the final handoff. Run those exact pinned
source files; a source copy at another path needs its own prepared handoff.
No active V2 or frozen V1 core, protocol, driver or study file is modified here.

Device no-fit is explicit: stream data above 32,768 B is a data-alone failure;
smaller data gets its complete actual link. Linked overflow is separate from
other errors and from timing/output failures. No source is trimmed, compressed
again or replaced to make a player fit. Portable C stays selectable; measured
real-time support belongs only to the existing explicit ASM profile in simavr.

## Commands

Supply the prepared runtime/dependencies and use fresh ignored output names.
Final preparation requires the actual audit PASS, exact executing auditor,
existing frozen consumer preparation and immutable prior evidence:

```sh
python reproduction/prepare_union.py \
  --source-root "$LPX_FROZEN_CONSUMER_ROOT" --study "$LPX_COMPLETED_V2_STUDY" \
  --output "$LPX_FINAL_HANDOFF" --public-output "$LPX_FINAL_SCOPE_JSON" \
  --final --audit "$LPX_INDEPENDENT_AUDIT" --auditor-source "$LPX_EXACT_AUDITOR" \
  --prepared "$LPX_PLAYER_PREPARATION" --expect-scope scope-estimate.json \
  --prior "$LPX_PRIOR_V1_IMAGES" --prior "$LPX_PRIOR_ROUGHNESS_IMAGES" \
  --prior "$LPX_PRIOR_ADAPTIVE_TARGET_IMAGES"
```

After final preparation and scope agreement, run each shard using the same
handoff and campaign output. Do not launch from the preliminary estimate:

```sh
python reproduction/measure_union.py run --source-root "$LPX_FROZEN_CONSUMER_ROOT" \
  --handoff "$LPX_FINAL_HANDOFF" --output "$LPX_PLAYER_CAMPAIGN" --shard 0
python reproduction/measure_union.py run --source-root "$LPX_FROZEN_CONSUMER_ROOT" \
  --handoff "$LPX_FINAL_HANDOFF" --output "$LPX_PLAYER_CAMPAIGN" --shard 1
python reproduction/measure_union.py aggregate --source-root "$LPX_FROZEN_CONSUMER_ROOT" \
  --handoff "$LPX_FINAL_HANDOFF" --output "$LPX_PLAYER_CAMPAIGN"
```

`test_protocol.py` covers exact cap/phase deduplication, ordered reset identity,
ineligible/oversized rejection, whole-data no-fit without truncation and the
pending/partial audit gate using synthetic streams. These six contracts build
no firmware and fit no source. Keep assertions enabled. This package contains
no source audio, encoded media, firmware or private identity/fingerprint values.
