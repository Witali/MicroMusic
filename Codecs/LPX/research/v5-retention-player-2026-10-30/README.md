# Canonical retention: player extension

Preparation only. No new images or playback claims are recorded here yet.

`reproduction/prepare_retention.py` verifies the final zero-fit 118-record replay,
reconstructs its genuinely new automatic selections and exact declared-level
rollbacks, and freezes a finite handoff for the unchanged prior union dispatcher.
It never builds or simulates a player. Both terminal replay shards, their final
export and the exact prior 75-chain player proof are mandatory inputs.

See [PROTOCOL.md](PROTOCOL.md). The prior package retains the executed generic
dispatcher and strict artifact checks. This extension preserves its fixed
16 MHz/8 kHz explicit-ASM, queue 256/prefill 192, IRQ 0/+100 configuration.
Playback admission is separate from subjective quality adoption.

Five preparation contracts pass: raw eligibility, cap/tie ordering, invalid
whole IDs/objectives, ordered-byte identity and duplicate inventory rejection.
The contracts import no codec and perform no fitting, decoding or image work.

Preparation accepts explicit `--source-root`, `--export`, `--replay-source`, `--postcheck`,
`--shards SHARD0 SHARD1`, `--prior-handoff`, `--prior-proof`, `--output` and
`--public-output`. Use fresh ignored output names. The prepared private handoff
then supplies `--handoff` to the unchanged generic `measure_union.py` actions
`run --shard 0`, `run --shard 1` and, after both terminal receipts, `aggregate`.
Every action also takes the frozen `--source-root` and one fresh campaign
`--output`. Do not launch those actions for an empty new-selection scope.
