# Remove bounded power-of-two products before rounding

On classic AVR5 / ATmega328P, first simplify exact fixed-point arithmetic,
then select an existing narrow-result C/ASM primitive. The Speex five-symbol
noise table uses Q14 products for +/-128 and +/-256, followed by a left shift
of seven and rounded shift of fourteen. For a nonnegative scale <=121000000,
the high component fits signed16 and the shifted product fits signed32.

Floor nesting reduces the +/-128 cases to `(+/-scale+8192)>>14` and the
+/-256 cases to `(+/-scale+4096)>>13`. Keep negative-half rounding toward
positive infinity; negating the positive rounded word would be wrong.
The caller has 32 scales, maximum 115088100. This proof is not a generic
replacement for Q14 multiplication outside the bounded domain.

[Common table code](../../Codecs/Speex/AVR/src/lowrate_noise.c),
[shared word-shift template and C fallbacks](../../Codecs/Speex/AVR/src/avr_shift.h).
The new 13-bit specialization keeps only observable result bits 13..28.
Architecture plus separate explicit ASM enable selects the AVR backend;
disabled/unsupported targets use C. Hardware memory access stays independent.

AVR GCC 7.3.0, GNU ABI, Os/LTO/mcall-prologues/mrelax, avr8js 0.21.1:
228595 scalar scales match old ASM, new ASM, explicit C and independent
original-equation arithmetic. ABI/r1, output guards and readonly inputs pass.
The scalar call takes 729 -> 98 cycles and 32 -> 0 MULs; full decoder runs save
640 cycles/frame (0.620% NB2.15 / 0.270% WB3.95), 86 B Flash in each image,
and 2 B NB stack. Both complete 10627-frame corpora retain exact PCM/reset.
Separate active-output admission passes 10627 WB IRQ frames with 8% added
CPU work and 3600 actual SPI frames: exact s16/PWM, zero underruns, minimum
queues 7 / 33, 411 / 408 B free SRAM. No board timing is claimed.

Original project technique; retain existing Xiph algorithm/table BSD notices.
[Proof, bounds, measurements and next candidates](../../Codecs/Speex/AVR/WB_NOISE_SHIFTS.md).
