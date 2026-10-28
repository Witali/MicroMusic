# Expanded legacy winners: complete AVR release check

The expanded-legacy selected winners from this tuning pilot pass the full
release player at normal and **+100 cycles per audio IRQ**, without increasing
their paired full Flash or static SRAM. All eight unique images produce the
complete expected 64,000-sample PWM sequence with exact ticks/EOF and zero
underruns or decoder/observer errors.

Scope is the same one tuning recording in profiles 4/6: its achieved-size
baseline and the accepted expanded-legacy selected stream, each as one ROM
segment. The expanded search uses 64 anchors, four spectral finalists,
1280-sample lookahead, 160-sample excitation horizon and two passes. Its
whole-reference PCM SSE changes from 45,184,014,310 to 43,894,102,578 (p4),
and 25,280,506,238 to 24,094,467,014 (p6), while satisfying the existing
PCM/PWM SSE/STOI automatic floors. This does not establish audibility.

The current release recipe is ATmega328P / AVR5, 16 MHz / 8 kHz, v5-only,
explicit ASM, LPC segments 2, queue 256 / prefill 192, AVR-GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, unroll 1 / tuning 0. MCU source is
byte-identical to `5c7e0592`; player/config are the selected release recipe
from `22e50e01`. Vendor headers and target/toolchain source inputs are pinned.
The established external observer uses vendor-derived unlinked metadata and
real playback state; no diagnostic globals are added to the production ELF.

| Profile | Extra IRQ cycles | Baseline and expanded full Flash | Program excluding exact stream | Stream bytes | Static SRAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 | 0 | 8,120 B | 4,573 B | 3,547 B | 756 B |
| 4 | 100 | 8,128 B | 4,581 B | 3,547 B | 756 B |
| 6 | 0 | 9,756 B | 4,575 B | 5,181 B | 756 B |
| 6 | 100 | 9,764 B | 4,583 B | 5,181 B | 756 B |

Each table row represents two independently linked and played images. There
are four distinct streams and eight distinct stream/IRQ combinations; none
were duplicate work. `.data` is zero, so `.text` equals full Flash; `.bss`
and static SRAM are 756 bytes. Exact embedded stream arrays and byte ranges
are proved before subtracting audio from the complete linked image. Program
size includes decoder, tables, player, reset-chain metadata and linker effects;
it is not a standalone library footprint. Per-profile placement/linker costs
are measured rather than inferred from source or payload length.

Every image reports 64,000 produced and played samples, 64,000 timer events
and ticks, terminal EOF/stopped, empty queue, and zero underruns/errors. Full
PWM equals that generated from the independent complete integer model. The
native common and compact-only PCM/PWM parity checks are retained in the
preceding pilot audit. The minimum observed queue before producer EOF is 192;
minimum observed startup/prefill and playback stack margin is **1,231 bytes**
for all eight images. Observed PWM intervals are 1,995–2,005 CPU cycles around
the 2,000-cycle timer period; maximum observed IRQ duration is 68 cycles
normal / 168 cycles with the added load.

The [anonymous source-bound receipt](expanded-release.json) includes every
image's complete Flash/program/data/SRAM/stack and timer evidence, full
PCM/PWM metrics, actual compiler flags, public source/toolchain/vendor hashes
and loaded host-runtime bindings. Private ELF/HEX/maps, stream/PWM data,
recording paths and media-derived fingerprints remain in ignored build.

This admits only these accepted expanded-legacy streams on the stated
simulator recipe. It does not admit raw beam, perceptual or price alternatives,
and makes no physical-board, analog or listening-quality claim. Portable C
remains selectable; the real-time evidence here applies to explicit ASM.
