# Standalone v5 player and external AVR observation


The selected standalone default is **FIFO 256 / prefill 192**. With the frozen
final decoder `5c7e0592`, the complete program occupies **4,573–4,600 B**,
excluding exact embedded audio, and **756 B static SRAM**. All 111 normal and
5 extra-100-cycle IRQ runs pass full model/frozen PWM, exact ticks and EOF,
with zero underruns. Full Flash including payload is 5,094–27,858 B.

| Paired application build | Program Flash excluding exact audio | Static SRAM |
| --- | ---: | ---: |
| Fixed-tail core, standalone 512 / 384 | 4,959–4,988 B | 1,059 B |
| Fixed-tail core, standalone 256 / 192 | 4,757–4,784 B | 801 B |
| Final core, standalone 256 / 192 | 4,573–4,600 B | 756 B |

At the fixed-tail core, FIFO 256 alone saves **202–208 B full Flash** and
**258 B static SRAM**, after all 116 runs passed. Byte indices remove wider
index arithmetic and atomic publication/read sections, while the final
head+EOF publication remains atomic. The measured core change inside the
256 application saves another 182–184 B; the diagnostic application sees a
different core delta because LTO and application context differ.

The actual combined final image saves **410–498 B full Flash** and
**328–329 B static SRAM** against each exact fixed-tail diagnostic control.
The same final core with standalone 256 instead of diagnostic 512 saves
188–280 B Flash. These are separate whole-image comparisons; independent
range endpoints cannot be added to predict the final linked result.

Final minimum queue before producer EOF is 192; minimum observed stack margin
including startup/prefill is 1,231 B. Maximum audio IRQ duration is 68 cycles
normal / 168 cycles with the deliberate 100-cycle load. Complete PWM intervals
are 1,995–2,005 cycles around the 2,000-cycle timer period. Both the fixed-tail
and final 256 variants also pass 37 synthetic boundary/error/C cases, including
20/100-sample prefill aborts. The C check is short prefilled playback, without
a continuous 8 kHz C admission claim.

FIFO 128 / prefill 96 is **rejected before timing admission**: ten complete
linked-image pairs (the five exact stress chains, each at normal/+100 IRQ)
all grow Flash by 6 B and save only 128 B static SRAM. Flash is the primary
constraint and no smaller RAM limit requires that tradeoff. FIFO 128 has no
supported timing claim.

[Final anonymous summary and source pins](final256-summary.json),
[paired final rows](final256-rows.json), and
[bounded rejected-128 size screen](rejected128-size-screen.json).

## Preserved 512 baseline

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
