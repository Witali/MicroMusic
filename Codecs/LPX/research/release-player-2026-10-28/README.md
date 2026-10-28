# Standalone v5 player and external AVR observation

The fixed-tail decoder from `b8f473a6` is unchanged in this first comparison.
Replacing its diagnostic application with a standalone one-shot ROM player
saves **24–110 bytes of full Flash** and **25–26 bytes of static SRAM** on the
same 116 images at FIFO 512 / prefill 384. These are application savings.
They are not a reduction in the decoder core.

The player preserves the Timer1 CTC / Timer2 OC2B configuration, ordered reset
segments, full model PWM and terminal behavior. The production ELF retains
only needed playback state. The separate host observer obtains interrupt and
OCR-write notifications through simavr; vendor-derived address metadata is
compiled into an unlinked sidecar object, never into the AVR image.

| Fixed-core comparison | Diagnostic application | Standalone 512 / 384 |
| --- | ---: | ---: |
| Program Flash, excluding proven embedded audio | See paired rows | 4,959–4,988 B |
| Full image Flash, including exact payload | See paired rows | 5,480–28,246 B |
| Static SRAM | 1,084–1,085 B | 1,059 B |
| Paired full Flash saving | — | 24–110 B |
| Paired static SRAM saving | — | 25–26 B |

AVR5 / ATmega328P, AVR-GCC 7.3.0, 16 MHz / 8 kHz; v5-only, explicit ASM,
segments 2, unroll 1, tuning 0, `-Os -flto -mcall-prologues -mrelax`.
Full Flash is linked `.text + .data`. Program Flash subtracts only exact
embedded audio arrays, proved uniquely in symbols and binary ranges; it still
includes decoder code, tables, application code, stream pointer/size tables,
runtime and linker effects. LTO can inline decoder work into `main`, so symbol
sizes are not reported as an independently linked library footprint.

All **111 normal + 5 extra-100-cycle IRQ controls** pass complete model/frozen
PWM comparison, exact useful sample/timer/EOF counts, zero underruns, empty
queue at successful EOF, valid SPSC publication/consumption and no extra ticks.
The normal set covers 5,743,258 samples, without a 64,000-sample observer cap.
Minimum queue before producer EOF is 384; minimum observed stack margin,
including startup/prefill, is 916 bytes. PWM intervals across this matrix are
1,989–2,011 cycles around the 2,000-cycle timer period. These measurements
establish the declared simulator workload only.

Additional synthetic checks pass 57 cases across profiles 4/6: partial tails,
prefill and index-wrap boundaries, reset chains, initial and post-start errors,
and prefill errors after 20 or 100 valid samples. A prefill error starts no
timer and leaves the queued prefix unplayed; a post-start error drains valid
queued samples. An explicitly selected C backend passes a short prefilled
output check; continuous 8 kHz admission is for ASM only.

The direct observer test passes one valid control and rejects 65 malformed or
inconsistent descriptors before opening PCM/report output files. It checks all
27 fields at zero/out-of-range values, invalid parser input, overlapping or
wrong ELF state and incompatible queue dimensions. All numeric SRAM spans are
bounded before indexing simulated CPU memory. Player validation rejects stale
reports when a runner fails before producing new evidence.

A real cache characterization performs one AVR link and two observer runs
across initial build, cache hit, changed artifact-proof epoch and changed
validation epoch. The ELF timestamp remains unchanged during revalidation.
Toolchain/vendor header trees and AVR build inputs are bound separately from
host runner/model/runtime provenance.

[Numeric summary and public source/toolchain fingerprints](baseline512-summary.json)
and [anonymous paired rows](baseline512-rows.json) omit private recording IDs,
paths, media fingerprints and ELF/PWM binaries. Complete images, map files,
observer descriptors and private joins remain in ignored build storage.

The [player example](../../01_ACTIVE_Q0_CODEC/examples/AVR_V5_PLAYER/README.md)
contains build and observer commands. Existing diagnostic builders remain
available as controls. The exact private inventory, segment order and payload
bytes are held fixed for all paired measurements. No physical-board, analog
sound-quality or universal queue-size claim is made.
