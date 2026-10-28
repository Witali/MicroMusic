# LPX: let the size compiler share repeated arithmetic

Measured target: ATmega328P / AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0,
16 MHz / 8 kHz, unroll 1/tuning 0, compact-only, explicit ASM,
`-Os -flto -mcall-prologues -mrelax`. Removing forced `always_inline` from the
existing twice-called Q14 attenuation helper lets the compiler share one kernel.
Its exact floor, coefficient 0..16384/state signed16 contract and C/ASM selector
are unchanged. This is a call-boundary optimization, not new assembly.

On ten fixed complete real images it saves 38 B Flash with unchanged SRAM.
Eight before/after normal/+100 IRQ images have exact full PWM and zero underruns;
wall decode cycles rise 1.63-4.01%, observed after-ready stack margin stays 894 B.
No cross-toolchain, startup/worst-case or board claim follows. Fresh C/ASM/generic
AVR math checks cover 5,768,584 cases each with IRQ and zero r1 errors.

A static polynomial helper is already optimized equivalently by LTO. Rice
status/out/shape rewrites, a new spectrum helper, and cached-prefix factoring
are correct in their recorded differential checks but give no uniform Flash
benefit. Keep their source evidence rather than accumulating unused code flags.

[Measured sources, exact scope, rejected patches and reproduction](../../Codecs/LPX/research/small-kernels-2026-10-28/README.md).
