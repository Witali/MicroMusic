# Complete-player admission of encoder candidates

The frozen perceptual tuning pilot's baseline, SSE-selected/raw and
perceptual-selected/raw streams pass complete production-player simulation.
Thirty role requests deduplicate to 22 exact streams. Each was built and
played at normal and extra-100-cycle IRQ load: **44 images, 2,816,000 samples**.
All complete PWM outputs match the independent integer model, with exact
produced/played/timer-event/timer-tick counts, successful EOF, empty terminal
queue, zero decoder/observer errors and zero underruns.

| Actual linked player | Normal IRQ | Extra 100 IRQ cycles |
|---|---:|---:|
| Full Flash, including exact embedded audio | 8,112–9,810 B | 8,120–9,818 B |
| Program Flash, subtracting only proven audio arrays | 4,573–4,575 B | 4,581–4,583 B |
| Static SRAM (.data + .bss) | 756 B | 756 B |
| Initialized .data | 0 B | 0 B |

All 48 candidate/baseline paired image comparisons have **zero full-Flash
delta and zero SRAM delta**. The one raw candidate saving one serialized byte
does not reduce linked Flash: one byte of program/alignment accounting offsets
that saving. Stream bytes alone are not substituted for complete linked cost.
The `.text` values include code, read-only tables and embedded audio; they
must not be described as instruction-only code size.

Minimum observed queue before producer EOF is 192; minimum stack margin over
startup/prefill and playback is 1,231 B. Maximum observed IRQ duration is
168 cycles with the deliberate stress load. PWM intervals span 1,995–2,005
cycles around the 2,000-cycle audio period. Each image plays its full
64,000-sample stream; no historical diagnostic image or capped timing receipt
is used. [Exact anonymous rows and source/runtime binding](perceptual-pilot.json).

The separate allocator admission checks one tuning-only profile-4 swapped
candidate and its same-cap amplitude control, each **1,765 B / 32,000 samples**,
at both IRQ loads. All four images pass the same complete PWM/EOF/tick/error
checks. Both streams occupy **6,338 B full Flash normally / 6,346 B stressed**,
with 4,573/4,581 B program Flash and 756 B SRAM. This is a comparison within
the strict 95% stream cap; it is not a quality improvement claim against the
larger original incumbent. [Separate numeric receipt](allocator-same-cap.json).

The measured recipe is ATmega328P / AVR5, 16 MHz / 8 kHz, explicit ASM,
v5-only, LPC segments 2, unroll 1 / tuning 0, queue 256 / prefill 192,
AVR-GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`. Decoder bytes match
`5c7e0592`. The actual release-player builder proves unique exact audio ranges
in the linked binary and excludes profiler/observer-only symbols. Vendor
hardware metadata is compiled into an unlinked sidecar; a freshly compiled
external simavr observer reads only actual playback state and hardware events.
The numeric receipt binds compiler/vendor dependencies, loaded runtime
libraries, decoder/player/model/observer sources and the exact compiler flags.
Those sources and every linked image, saved PWM file and report were rechecked
after validation.

All recording paths, audio, stream/PCM/firmware fingerprints, ELF/HEX images
and detailed joins remain in ignored build storage. The public stream ordinals
only show deduplicated role relationships. These are bounded simulator results
for the stated controls. They do not establish physical-board/analog behavior,
audible improvement, continuous C-backend timing, other queue sizes, or full-
corpus/held-out admission. The perceptual pilot's existing quality-floor and
listening limitations remain unchanged.

For repetition, use `tools/build_release_player.py` with the hash-matched MCU
source, each original ordered stream, `--queue 256 --prefill 192 --enable-asm`
and `--irq 0` / `--irq 100`, plus the external observer produced by
`tools/build_release_observer.py`. The [player instructions](../../01_ACTIVE_Q0_CODEC/examples/AVR_V5_PLAYER/README.md)
describe the same build/observer interface. Reproducing these exact private
workloads additionally requires their locally retained stream inventory.
