# V2 complete-selection player union: finite protocol

This protocol precedes any union image build or simulation. It consumes the
frozen adaptive study; it performs no fitting, re-encoding, cap-specific search,
new quality selection or perceptual adoption. The user's target A/B listening
comparison was inconclusive. Passing playback does not adopt a larger stream.

## Input scope and final gate

Use the exact prepared V2 binding and its three declared phases: 98 speech
screen groups, 14 paired default-budget speech groups and six nonspeech groups.
All 118 records and six source-parity worker receipts must be complete before
final preparation. An independent V2 audit must pass and bind the same study
binding, complete record/marker inventory, selected bytes and 100/95/90 choices.
Pin the actual audit receipts; a detached status string is insufficient.

A preliminary estimate may inspect only immutable completed records before the
last worker finishes. It is explicitly unaudited and cannot authorize image
work. Pin each record/marker observed by that estimate and report missing jobs.
An estimate is not a reusable final handoff. Do not launch any image until the
complete-worker and independent-audit gates both pass.

Retain each automatically selected whole chain at the 100%, 95% and 90% integer
caps when its **ordered actual stream bytes differ from its whole rollback**.
The rollback is that same record's declared-level `control`: the accepted V1
chain for speech and original whole chain for nonspeech. Do not substitute the
original quiet recording for a declared amplified target. Keep mode, gain,
phase, targeted status and complete quality-gate scope explicit.

No automatic selection means no candidate. Identical selected/control bytes
are unchanged and are skipped. An ineligible raw tradeoff is never admitted;
an eligible `concat-raw` chain actually selected by the frozen whole rule is an
automatic selection and remains in scope. Do not search segment mixtures.

## Exact union and finite work

Verify every actual segment's fingerprint, stored length, profile, declared
samples, order and offset, and each complete chain's length and byte total.
Deduplicate by ordered stream bytes, not cap labels, filenames, source labels,
sample hashes or byte counts alone. Shared chains retain every selection view.
Deduplicate each resulting chain/configuration at normal and +100-cycle IRQ.

Include the exact rollback of every changed selected chain, deduplicating those
too. A chain can have both roles. Pairwise comparisons retain their own phase,
cap, mode/gain and targeted context even when playback images are shared.
No unchanged-only chain is rebuilt to increase the sample count.

The maximum logical image rows are exactly `2 * distinct_union_chains`. This
bound includes fit, reused, data-alone no-fit and linked no-fit rows. Record
actual newly built images, new simulations, strict reuses and failures separately.
The final handoff fixes this set; no quality-driven expansion or alternate
candidate is allowed after a playback failure.

Use two deterministic zero-based chain-index parity shards. Both IRQ loads of
one chain stay on the same shard. Image directories are isolated by chain and
IRQ; the prepared observer/toolchain and source files are read only. Shards
write separate attempt, row and result files. Aggregate only after both are
terminal complete and their exact handoff/source identities agree. This does
not change the finite union or count a reused image as a fresh simulation.

## Consumer and actual complete Flash

Use the frozen consumer epoch `5b4800f7`, whose MCU bytes match `5c7e0592`.
Confirm V2 decoder sources and actual native outputs are compatible with this
consumer before admission. Keep active V2 and frozen V1 guarded files unchanged.
The production target is ATmega328P/AVR5, 16 MHz/8 kHz, queue 256/prefill 192,
the existing explicit ASM recipe and AVR-GCC 7.3.0. Portable C stays selectable;
no new C real-time claim or ASM change is introduced.

Charge complete linked `.text + .data`, embedded streams, all reset metadata,
tables and code once per image. Report program excluding streams and static
SRAM separately. Never use the 4,574-byte single-stream program as a universal
constant: segment metadata and linked layout can change the result.

If actual embedded stream bytes alone exceed 32,768 B, record `no-fit-data-alone`
for each IRQ configuration without trimming or pretending playback was checked.
Such a direct-embedding image cannot fit even before program/metadata. Preserve
the full source chain in the handoff. For smaller data totals, attempt the exact
complete build; linker overflow is `no-fit-linked-flash`, with unavailable
complete-image size left null. Other compilation errors are failures, not no-fit.
Do not compress, truncate, drop resets or choose another stream to make it fit.

## Native, interrupt-active playback and reuse

For representable chains, verify complete ordered PCM16/PWM against the model
and common/v5-only native decoders. Every newly simulated fit image must pass
all physical PWM samples, produced/played totals, EOF, timer ticks/events,
empty final queue, errors, stack margin and zero underruns with interrupts active.
Expected samples cover the actual whole chain, including every reset and tail.
Report timing/output failure separately from size feasibility.

Reuse is allowed only through the retained strict `PlayerEvidence` proof:
actual source/build recipe, compiler/header/library/harness, configuration,
ordered embedded data, ELF/binary/HEX, observer/runtime, expected physical PWM,
report and validator must match. Prior artifacts are read only and retain their
original labels. A matching data length or producer filename permits no reuse.
New images inside this fixed campaign may be reused only after the same proof.

## Receipts and publication

Pin study binding, every used record/marker/stream, final audit receipts,
consumer preparation/source inventory, toolchain/runtime, dispatcher/helper
sources and prior evidence before work; verify pins again at completion.
Journal each attempt and row before build/simulation, including incomplete or
failed work. A completed cache is usable only after its exact prepared identity,
artifact fingerprints and full proof pass. Never restart solely on a poll timeout.

Save partial checkpoints privately. Public output uses anonymous chain/comparison
IDs and numerical outcomes; paths, source identities, audio/PCM/stream/image
fingerprints, generated firmware and logs remain in ignored build storage.
An anonymous read-only artifact export must pass before a focused commit.
No push is part of this task.

The preliminary scope estimate and this protocol decide the finite dispatch
set. Final implementation must bind the actual independent audit receipt schema
and pass its gate before the first image; this document alone is not admission.
