# Charge a new parameter syntax against the complete player

Measured isolated experiment: ATmega328P, AVR5, AVR-GCC 7.3.0, `-Os -flto
-mcall-prologues -mrelax`, unroll 1, function tuning 0, 16 MHz / 8 kHz,
256-byte FIFO and configured prefill 192. The existing explicit AVR ASM math
backend is unchanged; portable C remains separately selectable. Vendor Flash
access stays independent of arithmetic selection. No new ASM was written.

An experimental scale-repeat parser reuses the decoded lag-zero reset state
for the first absolute tuple, then retains the cached scale step on repeats.
The proof domain is the v5-style tuple lifetime: every later decoded lag is
18..145 even at zero gain. Encoded lag code 0 is valid and means lag 18. Raw
scale aliases must still survive lossless conversion. This is not a generic
legacy first-output sentinel. Reset, failed begin, sticky errors, value copies,
tail packets and alternate storage settings were checked.

Actual complete linked `.text + .data` includes tables, headers and embedded
audio. In 32 paired/control ASM images at normal/+100 IRQ, the added non-audio
cost is 45..47 B with unchanged 756 B static SRAM and a minimum observed stack
margin of 1,231 B (short synthetic controls: 1,240 B), unchanged per pair.
The four fixed tuning chains save only 10..33 B of data and therefore
**lose 14..36 B of complete Flash**. One 281,632-sample/five-segment chain saves
74 B of data and 28 B net. All 32 images have exact physical PWM/ticks/EOF/queue
termination and zero underruns; this does not establish a universal format win.

Both explicit-C 64,000-sample observations preserve the valid sample sequence
but underrun 36,410/36,416 times. They do not support 8 kHz real-time playback.
The independent audit checks 34 ELFs and 50 embedded regions. Production source
is unchanged; the patch materializes only in ignored build storage. New-format full corpus
expansion and simultaneous old/new decoder costs remain unmeasured and paused.

Original project experiment; original source provenance/licensing applies.
[Protocol, patch, exact recipe, anonymous results and audit](../../Codecs/LPX/research/v6-scale-repeat-2026-10-28/README.md).
