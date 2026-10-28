# Separate the AVR application from diagnostic instrumentation

Applicable scope: ATmega328P / AVR5, AVR-GCC 7.3.0 / AVR-LibC manufacturer
register definitions, 16 MHz / 8 kHz v5 LPX playback, explicit ASM arithmetic
backend. The production player is C++ and retains the library's default C
backend; its only inline assembly is a compiler memory barrier. This is not
a new arithmetic assembly backend.

Diagnostic firmware often couples useful playback control with counters,
markers and hardware-address globals. Replace the application control with
explicit producer-owned head/EOF/error and interrupt-owned tail/stopped, then
observe the linked image externally. Removing counters without preserving
termination, segment advancement and queue drain is not equivalent.

The producer writes an element before publishing head. The ISR reads that
element before publishing tail. A 512-entry queue needs atomic shared 16-bit
access; the later 256-entry experiment uses byte indices with natural wrap.
One slot remains empty. Final head and EOF must publish in the same atomic
section even when the indices are bytes: otherwise the final sample can drain
before EOF becomes visible and cause an extra empty output tick. Compiler
barriers express the ordering independently of atomic byte width.

The external observer hooks the public simavr 1.6 interrupt-entry/RETI and
OCR-write interfaces. A separately compiled object obtains address, vector
and timer configuration from vendor headers, but is not linked into the
production AVR ELF. Validate descriptor bounds and disjoint SRAM spans,
actual device-model registers and exact ELF symbols before reading memory.
Derive published/consumed counts, useful output, timer events, underruns,
queue minimum and stack observations without adding AVR diagnostic globals.

Measured fixed-core FIFO 512 / prefill 384 replacement: 24–110 bytes less
full Flash and 25–26 bytes less static SRAM on 111 normal + 5 active-IRQ
stress images. All complete PWM/ticks/EOF/queue checks pass, with zero
underruns. This is application savings; LTO and inlining prevent interpreting
it as decoder-library savings. The same source, compiler flags, ordered
payload and reset geometry are required for each pair. C arithmetic remains
selectable; the continuous 8 kHz admission applies to explicit ASM only.

[Implementation, ABI and reproduction](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/AVR_V5_PLAYER/README.md)
and [full measured scope and anonymous receipts](../../Codecs/LPX/research/release-player-2026-10-28/README.md).
The observer is original project code using an unchanged external GPL-3.0-or-later
simavr library; API references and licensing are linked from the example.
Simulator timing does not establish board/analog behavior.

The admitted 256 / 192 byte-index profile saves a further 202–208 B full
Flash and 258 B static SRAM at the fixed decoder, across the same 116 images.
Its capacities and final publication were checked at wrap and EOF boundaries.
With the final decoder, all 116 production images still pass; queue minimum
is 192, observed stack margin 1,231 B, and the actual combined Flash saving
against original diagnostic controls is 410–498 B. This total is measured,
not the sum of marginal range endpoints. The ten-image 128 / 96 cost screen
adds 6 B Flash everywhere while saving only RAM, so it is rejected before
expensive timing admission under the project's Flash priority.

## Measure encoder savings after final linking

New encoded parameters can change decoder workload even when MCU source is
identical. Compile and play the complete original and candidate reset chains;
count every header, array, pointer table, padding and linked program once.
Verify actual audio symbol ranges against binary bytes before subtracting
them from full `.text + .data`. A smaller serialized stream alone is not a
measured application saving.

The 2026-10-28 encoder study supplies two useful measured examples. Under
ATmega328P/AVR5, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`, explicit
ASM, LPC segments 2, unroll 1 / tuning 0 and FIFO 256 / prefill 192:

- One raw perceptual alternative saves one stored byte but no linked Flash:
  program/layout accounting absorbs that byte. The 44-image matrix checks
  complete 64,000-sample playback at normal and extra 100-cycle IRQ load.
- A held-out profile 4 candidate shrinks 1,800 to 1,701 stored bytes. Actual full
  Flash changes 6,374 to 6,274 B normally and 6,382 to 6,282 B under the extra IRQ
  load: 100 B saved, rather than the 99-byte payload-only prediction. Static
  SRAM stays 756 B. All four complete 32,000-sample PWM/EOF/tick runs pass with
  zero underruns; the candidate also preserves the original quality floors.

These differences include linked layout; they do not show new arithmetic
instruction savings. The C fallback remains explicitly selectable and MCU
bytes are unchanged. Timing admission here applies to the stated ASM profile
in simulation, not C real-time or physical-board/analog behavior. Encoder
rate prices may use serialized bits for proposals, but the final resource
frontier must use actual complete application measurements.

[Perceptual pair evidence](../../Codecs/LPX/research/v5-encoder-candidate-admission-2026-10-28/README.md)
and [held-out smaller-and-better pair](../../Codecs/LPX/research/v5-pareto95-player-admission-2026-10-28/README.md)
retain the original project method, source/toolchain provenance and exact
anonymous scope; private audio and media fingerprints stay in ignored build.
