# Audited adaptive selection union: complete-player admission

All **150 normal/+100 IRQ rows pass**. The fixed union has 75 distinct ordered
chains, with **132 new images and 18 strictly proven prior reuses**. All
6,924,372 physical samples match their own expected outputs, including every
reset and partial tail. There are zero device no-fit, timing/output or decoder/
observer failures and zero underruns. No fitting occurs in this stage.

For the 41 distinct same-level candidate/rollback comparisons, **31 have the
same complete Flash and 10 grow by 4..220 B**; none shrink. Growth is identical
at both tested IRQ loads. The encoder's original data caps do not imply a
proportional reduction of complete firmware or improvement over a smaller
accepted rollback. Numerical selection and playback do not prove audibility.

The finite preliminary scope was **75 distinct ordered chains / 150 logical
normal/+100 IRQ rows**, covering 42 changed automatic cap selections. It contains
41 distinct selected chains and 34 distinct declared-level rollbacks. Exact
byte deduplication merges overlapping phase/cap views while retaining all
comparison contexts. The maximum complete playback workload is 6,924,372
samples. The largest included chain has five reset segments.

The observed snapshot covered all 118 complete producer records and six worker
receipts. Of 354 cap views, 84 unchanged selections and 228 views without an
automatic selection require no candidate playback. The four changed nonspeech
views are retained; the long 60-reset nonspeech selections are unchanged and
therefore are not added to this union. No currently included chain exceeds the
device's Flash with stream data alone, but complete linking can still fail.

`scope-estimate.json` remains an immutable **pre-audit estimate**, not permission
to run images. `final-scope.json` records the subsequent actual 118-record audit
PASS, all six terminal workers and the unchanged accepted scope. Final
preparation bound their receipts, source and actual ordered bytes before work.
The [finite protocol](PROTOCOL.md) fixes the population, comparisons and gates.
Playback/cost evidence does not adopt a larger stream; the user's A/B target
listening comparison remained inconclusive.

## Actual complete costs

The table counts cap views, which overlap across phases/caps. It has 42 views
but only 41 distinct candidate/rollback pairs. The same table holds for normal
and +100 IRQ load:

| Phase | Original data cap | Changed views | Same full Flash | Larger full Flash | Full Flash growth, B |
| --- | ---: | ---: | ---: | ---: | ---: |
| speech screen | 100% | 27 | 23 | 4 | 0..220 |
| paired speech default | 100% | 10 | 4 | 6 | 0..220 |
| paired speech default | 95% | 1 | 0 | 1 | 8 |
| nonspeech default | 100% | 4 | 4 | 0 | 0 |

There are no changed automatically selected 90% views in this union. The ten
positive growth values per IRQ are 4, 8, 104, 104, 108, 110, 204, 204, 220 and
220 B. Program excluding streams changes by -1..+1 B within a comparison;
actual linked size includes stream parity/alignment and all metadata.

The one changed 95% view is the targeted profile-4 A stream: 1,710 B satisfies
`floor(1800 * .95)`, while its accepted declared-level rollback was already
1,702 B. Complete Flash therefore grows by 8 B relative to that rollback.
This is not a 5% full-firmware saving. It is the same A stream also selected
at 100%, with one image per configuration shared across those two views.

Across all images, complete Flash is **5,210..27,858 B**, program excluding
streams is **4,573..4,599 B**, static SRAM is **756 B**, and observed minimum
stack margin is **1,231 B**. The largest image is a profile-6, five-reset,
281,632-sample chain: 23,259 B of stream data and 27,858 B complete Flash at
+100 IRQ, leaving 4,910 B of device Flash. Reset metadata and linked layout
are charged; the single-stream program size is not reused as a constant.

The unchanged 60-reset nonspeech chain was excluded by the declared changed-
selection rule. This package makes no device-fit claim for it. The data-alone
and linked-overflow reporting paths are implemented, but no in-scope image
hits either limit. No recording is shortened to achieve a fit.

The target is ATmega328P/AVR5, 16 MHz/8 kHz with queue 256/prefill 192 and the
existing explicit ASM recipe using AVR-GCC 7.3.0. Consumer epoch `5b4800f7`
retains MCU bytes `5c7e0592`; producer epoch is `5a6cd1ab`. Portable C remains
selectable. These are interrupt-active simavr results, not C real-time,
physical-board or analog-audio measurements. Production costs exclude observer
instrumentation. No algorithm, format, ASM or source-level quality rule changes
occur in this measurement stage.

## Verification and receipts

Two parity workers completed 76 and 74 rows in timed regions of 307.34 s and
362.57 s. These regions ran in parallel and must not be summed as elapsed time.
Every fresh or reused image passes physical PWM, produced/played counts,
timer ticks/events, EOF/stopped state, empty final queue, error and stack checks.
New images cover 6,092,372 physical samples; proven reuses cover 832,000.

The read-only aggregate and final export reopen every source/build recipe,
toolchain/header/runtime binding, ordered embedded data, ELF/binary/HEX,
observer report and full expected output. Common and v5-only native PCM16/PWM
are rechecked against the model. Both campaign attempts are complete with no
failed attempts. No additional AVR build, simulation or fit occurs during export.

`summary.json`, `rows.json` and `source-runtime.json` are exact anonymous
projections of the completed aggregate. `cost-summary.json` records the cost
distribution, and `artifact-check.json` records the final proof. Actual paths,
source identities, media/PCM/stream/image fingerprints, generated firmware and
logs stay in ignored build storage. Public hashes identify code or generic
tool/runtime dependencies. Exact executed sources and shared helper digests
are listed in `reproduction/sources.json`.

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
