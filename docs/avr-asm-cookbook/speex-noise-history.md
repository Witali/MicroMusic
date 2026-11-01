# Reuse dead excitation history for transient data

Original project lifetime optimization, tested on ATmega328P / AVR5 at 16 MHz,
AVR GCC 7.3.0, GNU ABI and existing Os/O2/O3/LTO options. No new handwritten
ASM or CPU-specific memory access is introduced. Explicit C arithmetic fallback
selection stays unchanged. Speex/Xiph BSD provenance remains in the codec.

Prove which part of an existing buffer is dead before adding a second buffer.
Here a 145-word prior history precedes 160 current excitation words. A 40-sample
delay means synthesis first reads old word 105; the first 210 bytes are dead.
The next frame's history move reads from word 160, so overwriting bytes 0..169
cannot alter that move. NB1 vocoder construction itself reads no pitch history.

Use bytes 0..159 for the classes it already generates, then words 80..84 for
their five scaled values. The current excitation starts at byte 290. HB1 can
read this immutable bank instead of running another 160 RNG transitions and
four additional scaling passes. The shadow RNG seed is unnecessary too.
This is storage reuse; the 32-bit generator and all sample precision remain.

Assertions must bind both live boundaries, not only the total allocation size.
Test changing codec modes, delayed input, the next history move, reset and
rejected calls. The observation application injects guard bytes only into the
dead gap, checks cache/output immutability and validates classes, values and
seed progression against independent equations. Then compare complete PCM/PWM
with interrupts and storage active before claiming playback support.

Measured initial 384-frame screen: 257745.846 -> 243283.622 cycles/frame,
Flash 24804 -> 24726 B, static SRAM 1288 -> 1284 B, peak stack 210 -> 199 B.
The [full evidence and constraints](../../Codecs/Speex/AVR/WB_NOISE_REUSE.md)
identify the exact workload, admission stage and implementation. This layout
is specific to the restricted 160/40 profile; do not assume it holds for PLC,
another synthesis delay or a decoder retaining additional history.

Final admission passes 10627 exact WB frames, 21254 continuous active-IRQ frames
at normal/+8% work, and 5800 SPI frames across WB3.95/WB12.8, with zero underruns.
WB3.95 speech CPU is 75.60%, down from 80.12% before this reuse. The current
SPI example leaves 412 B SRAM. Simulator measurements do not establish board
timing; the observed +8% queue minimum is only two samples.
