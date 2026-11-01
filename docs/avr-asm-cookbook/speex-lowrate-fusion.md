# Reuse a fused vector kernel with a different codebook geometry

Target: classic AVR5 / ATmega328P, hardware MUL/LPM/MOVW, GNU AVR ABI,
AVR GCC 7.3.0, existing Os/O2/O3, LTO/mcall-prologues/mrelax, avr8js 0.21.1.
Original project template/control work; Xiph codebook/algorithm BSD notices
remain in the codec/vendor files. No board/analog measurement is claimed.

WB5.75/WB7.75 originally reconstructed forty excitation words with four
ten-sample calls, stored them, then reloaded/folded them in place. Reuse the
existing fused NB3/NB4 template and keep each value in registers through all
three original quantizers:

```asm
WB_EXCITATION speex_wb_excitation_nb2_40_avr,4,10,exc_10_16_table
WB_EXCITATION speex_wb_excitation_nb8_40_avr,2,20,exc_20_32_table
```

The signed shape/scale floor, signed16 intermediate, Q15 floor, modulo32
rounded scale and final parity remain distinct. All vector widths are even,
so local parity matches global parity. Forty-sample geometry is asserted.
The rounding bias stays **4**, independent of a vector count of 2, 4 or 5.
Do not halve a width 20 row just because the old helper accepted ten samples.

Index width and address width are separate: `31*20=620` requires the high
byte of MUL even though the index is uint8. The real template retains it in
Z and uses near LPM only inside the tested 32 KB image. Preserve all GNU
callee registers, including overlapping argument registers, and clear r1 at
return. Keep interrupts enabled and Flash access separate from arithmetic
backend selection. An explicitly callable C two-pass reference remains
selectable on AVR and unsupported/default architectures.

A tiny mode dispatch has only one production caller. Inlining it reuses an
existing mode branch and omits a five-argument boundary, while arithmetic
remains in shared-source, out-of-line ASM kernels. Measure both choices:
the selected inline version saves another 124/128 cycles/frame, 22 B Flash
and 3 B stack versus its outlined counterpart.

The 52256-case four-path test compares the original two-pass ASM procedure,
explicit C, test-wrapped inline dispatch and direct leaves against independent
BigInt equations and pinned codebook bytes. All table rows, 49 scales including
32 caller scales, signed gain boundaries and random cases pass. Actual LPM
addresses and index-read bounds are observed. SRAM hooks prove that each
fused quarter has 0 output byte reads / 80 writes versus 80/160 before.
That removes 640 SRAM byte accesses/frame. Valid argument registers stay intact
while other saved registers are randomized; 156768 ABI/r1 returns pass.

Matched complete WB5.75/WB7.75 images save 3252/3428 cycles/frame, improve
natural speech time 1.34%/1.41%, and reduce peak stack 20 B. Static SRAM stays
unchanged; the all-feature image grows 236 B Flash. Separate complete decoder,
loaded IRQ and SPI runs verify exact PCM/PWM and zero underruns. C decoder
controls are compile/link only; isolated C arithmetic is executed.

[Shared template](../../Codecs/Speex/AVR/src/wb_excitation_kernel.inc),
[instantiations](../../Codecs/Speex/AVR/src/wb_fold.S),
[C fallback/dispatch](../../Codecs/Speex/AVR/src/wb_fold.h),
[access/ABI observer](../../Codecs/Speex/AVR/tests/verify_low_fusion.mjs),
[complete measurements and reproduction](../../Codecs/Speex/AVR/WB_LOW_FUSION.md).
