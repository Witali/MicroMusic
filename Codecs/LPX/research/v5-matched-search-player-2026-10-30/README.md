# Matched-search ROM player gate

This is the complete-player stage for the saved single-path LPC versus trajectory
comparison. It performs no fitting, refinement or endpoint search. The numerical
study, ROM player feasibility, external-SPI feasibility and listening adoption
are separate claims. [PROTOCOL.md](PROTOCOL.md) fixes this stage before images.

The prepared finite union contains 187 exact ordered reset chains: 105 changed
automatic selections and 82 strongest same-level canonical rollbacks, with no
role overlap. It covers 112 changed arm/tier/cap views; those views overlap and
are not independent sources. Two IRQ configurations per chain give 374 rows.
Twelve rows have more than 32768 bytes of stored data alone and require no forced
ROM build. Their full 60-reset chains and samples remain in the scope.

The original 118-record independent audit is a source prerequisite. A separate
preparation gate reopens the final 248-arm/312-helper/744-cap matched-search study,
104 common baseline contexts, exact changed-selection inventory and new-study
cache provenance. Both gates must pass; one cannot stand in for the other.
The 8-second views retain and charge prior 2-second work as cumulative 2+8.

The frozen shared dispatcher builds ATmega328P images at 16 MHz/8 kHz, with explicit
ASM, a 256-byte queue, prefill 192 and IRQ loads 0/+100. C arithmetic remains an
available production fallback, but this campaign does not establish C timing.
No MCU source is changed by this measurement stage. Only positive prior proofs
with the exact ordered bytes, IRQ, compiler recipe, consumer source, runtime,
ELF/HEX/data and complete physical output may be reused. Matching byte lengths,
labels or an old PASS message is insufficient.

Playback runs in the pinned simavr observer with interrupts active. Fit images
must prove complete model/common/v5 PCM16 and PWM, produced/played
samples, EOF, timer ticks/events, drained queue, positive stack margin and zero
decoder/observer errors and underruns. Complete Flash includes the stored stream,
metadata, tables and program. Report program Flash excluding the stream and static
SRAM separately. A data-only no-fit, linked-Flash overflow, or observed output/
timing failure is retained as a negative result. No reset or tail is dropped.

Preparation lives in [reproduction/prepare_player.py](reproduction/prepare_player.py).
It accepts explicit `--source-root`, `--export`, `--trial-source`, `--preflight`,
`--shards SHARD0 SHARD1`, `--producer-commit`, `--prior-handoff`, `--prior-proof`,
`--retention-handoff`, `--retention-proof`, `--output` and `--public-output`.
Outputs must be fresh; a copied scope summary alone does not authorize images.
Six pure preparation contracts cover strongest canonical choice, stable ties,
separate levels, exact ordered bytes/rollbacks and duplicate-context rejection.
They perform no fitting, decoding or player work.

Original image execution uses the unchanged
[shared dispatcher](../v5-adaptive-player-union-2026-10-30/reproduction/measure_union.py).
The matched-scope [read-only exporter](reproduction/export_artifacts.py) reopens
all final artifacts without new AVR builds or simulations. Its scope comes from
the final handoff rather than the older dispatcher's original 75-chain campaign.
Private handoffs, inputs, streams, media, images, logs and fingerprints remain in
ignored build storage; only anonymous numeric evidence and source/toolchain
provenance are published here.

Run the frozen dispatcher from the prepared consumer checkout, once per declared
shard, with both IRQ rows of each chain kept together:

```text
python build/encoder-quality/run.py SHARED_PACKAGE/reproduction/measure_union.py run --source-root . --handoff HANDOFF --output CAMPAIGN --shard 0
python build/encoder-quality/run.py SHARED_PACKAGE/reproduction/measure_union.py run --source-root . --handoff HANDOFF --output CAMPAIGN --shard 1
```

One original worker encountered a Windows access-denied error while atomically
replacing its journal after 91 passing rows, before the next image began. Its
journal, failure receipt and completed proofs remain unchanged. The separate
[bounded recovery](reproduction/recover_player.py) binds that original state,
strictly reopens its completed prefix without simulation, and processes only
the 97 original pending rows. It retries atomic replacement at most six times,
only for Windows errors 5/32; other errors propagate and incomplete writes stay
preserved. The other original worker completed unchanged. Recovery and artifact
receipts report the failed attempt and mapping explicitly.
Five pure recovery contracts check recognized error retries, immediate propagation
of other errors, bounded exhaustion, preservation of incomplete files and the
exact positive-prefix/suffix boundary.

This campaign aggregates through the recovery dispatcher, preserving the failed
original rather than rewriting its status. After the unaffected worker and
recovery are terminal complete, run:

```text
python build/encoder-quality/run.py MATCHED_PACKAGE/reproduction/recover_player.py aggregate --source-root . --handoff HANDOFF --campaign CAMPAIGN --recovery RECOVERY
```

Then execute the matched read-only exporter:

```text
python build/encoder-quality/run.py MATCHED_PACKAGE/reproduction/export_artifacts.py --source-root . --handoff HANDOFF --campaign CAMPAIGN --recovery RECOVERY --package MATCHED_PACKAGE
```

Never restart an existing attempt because a tool poll times out. Inspect its
process, journal and retained artifacts before any explicit audited recovery.
Artifact receipts distinguish new simulations from strict prior reuses; total
proven samples do not mean every reused sample was played again in this stage.
Full-Flash growth means candidate minus its exact same-level rollback. Report
growth only for comparison pairs whose two images are admitted. This gate alone
does not establish physical-board or analog-output behavior, audibility, or a new
default algorithm.
