# Complementary coefficients: one product instead of two

For a fixed-point mean with `a+b=2^Q`, rewrite
`round((a*old+b*value)/2^Q)` as `old+round(b*(value-old)/2^Q)`.
Keep the original rounding bias. Prove the input difference's width before
narrowing it; two signed16 inputs can differ by a signed17 value.

In the Speex NB1 mean, `a=26214`, `b=6554`, `Q=15`, bias=16384. A wrapped
signed16 difference loses +/-65536, contributing an exact +/-13108 to the
result. On classic AVR5, SUB/SBC's V flag detects overflow, and the wrapped
sign selects its direction. LDI preserves V/N; CLR would destroy them.
One full signed16 product then replaces two, with unchanged feedback state.

Original [GNU ABI routine](../../Codecs/Speex/AVR/src/lowrate_mean.S),
[original C fallback and explicit backend selection](../../Codecs/Speex/AVR/src/lowrate_mean.h).
Target ATmega328P / AVR5 with MUL, AVR GCC 7.3.0. The 82-byte leaf uses only
call-clobbered r18..27 and flags, clears r1, adds no local stack and does not
mask interrupts. Keep manufacturer/compiler architecture macros and a separate
explicit ASM-enable define. Unsupported/disabled ASM defaults to C.

Measured with existing Os/O2/O3, LTO/mcall-prologues/mrelax, avr8js 0.21.1.
1,212,335 isolated pairs match BigInt and scalar AVR C, including complete
word sweeps at nine boundaries per operand, both overflow directions and
arbitrary callee-saved patterns. Each call executes four MULs, taking 43..48
cycles including RET. No C decoder runtime test is involved.

The matched 384-frame RU/EN/coverage screen saves 1.219% WB3.95 frame cycles,
44 B Flash, with unchanged SRAM/stack; NB2.15 saves about 3771 cycles/frame,
86 B Flash and 6 B stack. PCM is exact. These are screen measurements,
not a physical-board or complete active-output admission.
[Proof, scope and reproduction](../../Codecs/Speex/AVR/WB_MEAN_PRODUCT.md).

The subsequent complete affected-mode admission passes 21254 raw frames,
10627 WB IRQ frames with 8% additional CPU work, and 3600 long SPI frames:
exact PCM/PWM, zero underruns, minimum queues 6 / 32. Natural speech improves
3.53% NB2.15 and 1.23% WB3.95. Two 1024-frame mixed API runs observe 160 calls
and exactly 640 mean MULs per valid NB1 frame, with independently checked
results; rejected calls and other modes execute none. Four disabled-mode
images and both compile/link-only C controls remain byte-identical.

This technique is original project work. Preserve existing algorithm/table
licenses when adapting its surrounding codec; do not assume the correction
is integral for arbitrary coefficients, input widths or Q formats.

## Unmeasured follow-up: power-of-two noise scales

The current five-symbol noise table computes Q14 products for `a=+/-128`
and `+/-256`, then applies a left shift of seven and rounded shift of fourteen.
For the caller's nonnegative `scale <=121000000`, the signed16 high component
of Q14 fits and the shifted product cannot overflow signed32. Floor nesting
then suggests the exact closed forms `(scale+8192)>>14`, `(-scale+8192)>>14`,
`(scale+4096)>>13`, `(-scale+4096)>>13`, plus zero. This would eliminate the
remaining products in this once-per-frame preparation. Negative half-way
rounding must remain toward positive infinity; do not simply negate the
positive result. This is an algebraic candidate only: no implementation,
assembled check, measured saving or new real-time admission is claimed.
