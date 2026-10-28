# Frozen V1 changed-selection player union

All **32 image rows pass** complete production-player validation: 16 exact
unique chains at normal and +100-cycle IRQ load. The campaign builds/simulates
28 unique new images and proves four read-only reuses of the earlier research
target pair. Every physical PWM sample, EOF, produced/played count, timer
tick/event, empty queue termination and stack check passes with zero underruns,
decoder errors or observer errors. No size-limit or timing failure is dropped.

This follows the [independent saved-output audit](../quiet-voice-v1-independent-audit-2026-10-28/README.md).
V1 core `5b4800f7` remains frozen, with MCU decoder bytes unchanged from
`5c7e0592`. No new fit, candidate, format, ASM or V1 source change occurs here.

## Exact admitted scope

The audit has zero changed preserve-level selections at any cap: the 98 full-
budget selections are original controls. They are not remeasured as new work.
Auto-declared-target selections number 8/4/0 at 100%/95%/90%. Their union is
eight distinct changed chains plus eight original-level controls, covering
12 selected cap rows. Equal ordered byte chains are measured once per IRQ load.

All eight changed chains differ from their original-level quiet controls, but
seven are the fresh declared-target legacy control itself. Only one targeted
profile changes from that fresh control. Eligibility under frozen whole-chain
floors is not a claim that all eight improve the encoder algorithm. The
targeted source's two profiles remain targeted, not independent held-out data.

The admission projection retains `quality_adopted_at_frozen_study: false` for
the frozen auto research scope; earlier measurement labels remain immutable.
The user's later
operational choice to amplify quiet input is separate; playback validation
does not retrospectively change study labels or assert original-level quality.
Each waveform matches its own current model; the amplified waveform is not
claimed to equal its original-level control. No mixed-level quality aggregate
or audibility improvement is reported.

## Complete Flash and level distinctions

The table uses anonymous comparison ordinals. Gains are declared input gains;
the old control playback gain is 1. Net full-Flash savings are identical at
normal and +100 IRQ load. Positive saved bytes mean a smaller complete image.

| Comparison | Profile | New input gain | Original / candidate data, B | Selected original caps, % | Full Flash saved, B | Program change, B |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| 1 | 4 | 16 | 3,580 / 3,361 | 100, 95 | 220 | -1 |
| 2 | 6 | 16 | 5,006 / 5,003 | 100 | 4 | -1 |
| 3 | 4 | 32 | 3,532 / 3,328 | 100, 95 | 204 | 0 |
| 4 | 6 | 32 | 4,956 / 4,956 | 100 | 0 | 0 |
| 5 | 4 | 16 | 1,806 / 1,696 | 100, 95 | 110 | 0 |
| 6 | 6 | 16 | 2,621 / 2,516 | 100 | 104 | 1 |
| 7, targeted | 4 | 64 | 1,800 / 1,702 | 100, 95 | 98 | 0 |
| 8, targeted | 6 | 64 | 2,519 / 2,519 | 100 | 0 | 0 |

Full linked Flash is `.text + .data`, including exact stored audio, all headers,
tables, directories and linker layout. It spans 6,270..9,590 B across the
matrix; program excluding embedded streams spans 4,573..4,584 B. The -1/0/+1 B
program deltas are actual linked layout effects, not a decoder-body change.
All images fit 32,768 B Flash. Static `.data + .bss` remains 756 B and observed
minimum stack margin remains 1,231 B in all 32 rows.

The matrix checks 1,536,000 physical output ticks, including 1,408,000 ticks
from the 28 new images and 128,000 from the four reused images. Both native
common/compact PCM16 and PWM are checked against the current model and the
audited whole-chain fingerprints before AVR admission. Actual reset geometry,
source files and whole-chain bytes remain bound.

The target is ATmega328P/AVR5, 16 MHz, 8 kHz, queue 256 and prefill 192. The
current AVR-GCC 7.3.0 size recipe retains existing explicit ASM gating and
vendor memory access. Portable C remains selectable; this matrix does not
claim C real-time support. Observer metadata is not linked into production.
Results are from simavr, not a physical board or analog audio measurement.

## Reuse, checkpoint and evidence

The earlier target pair is reused only after matching current source, compiler,
headers/libraries, harness, complete build recipe, ordered embedded bytes,
ELF/binary/HEX identities, symbol/observer metadata, runtime/model expectation,
report, full physical PWM and the strict current validator. Its folder is
read only. Reuse is counted explicitly, not called a new build or simulation.

An initial host reuse check stopped after 24 completed new images because its
expected runner descriptor used the diagnostic default. The final helper
assigns the exact `sim_player.c` descriptor used by current `player.simulate`;
full equality remains strict. Those 24 ELF/report/PWM/fingerprint artifacts
are revalidated unchanged before completion. The original checkpoint/helper
remain private. The summary's 45.14 s describes the resumed validation and
completion pass, not the unrecorded total campaign wall time. New-image counts
refer to unique images over the entire campaign, including that checkpoint.

`summary.json`, `rows.json` and `source-runtime.json` retain exact anonymous
completed projections. `artifact-check.json` records the read-only final
source/toolchain/runtime/image/expected-output check and unchanged checkpoint.
Private media, identities, paths, per-recording/firmware hashes, images and logs
remain under ignored build storage. Public hashes identify source or generic
tool/runtime dependencies only.

The exact final executed union generator and admission helpers are retained in
`reproduction/` with `sources.json`. Their source bytes match the receipts.
The union is derived solely from independently audited changed selections,
keeping every source mode, gain, cap, targeted flag and whole-gate scope. Failed
admission or actual linked Flash overflow stays a visible row.

For a later authorized reproduction, use Python 3.12 and the pinned V1 source
and runtime, completed private study/audit, source-bound player preparation,
and prior frozen target evidence. Run from the repository root and keep all
generated artifacts in ignored build storage:

```sh
python Codecs/LPX/research/quiet-voice-v1-player-union-2026-10-28/reproduction/player_union.py \
  --source-root "$LPX_V1_SOURCE_ROOT" --study "$LPX_V1_STUDY" \
  --audit "$LPX_V1_AUDIT" --prepared "$LPX_PLAYER_PREPARATION" \
  --output build/v1-player-union-handoff-private.json
python Codecs/LPX/research/quiet-voice-v1-player-union-2026-10-28/reproduction/measure_union.py \
  --source-root "$LPX_V1_SOURCE_ROOT" --study "$LPX_V1_STUDY" \
  --audit "$LPX_V1_AUDIT" --handoff build/v1-player-union-handoff-private.json \
  --prepared "$LPX_PLAYER_PREPARATION" --prior "$LPX_FROZEN_TARGET_IMAGES" \
  --output build/v1-player-union-admission
```

Do not disable assertions with Python optimization flags. No private handoff
or firmware binary is included. This is V1 admission evidence; future unified
or roughness search and later operational defaults are separate work.
