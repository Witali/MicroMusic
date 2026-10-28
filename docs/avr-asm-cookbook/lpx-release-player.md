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
