# Exact finite-domain noise and narrow observable state

Original project optimization of the Xiph Speex 1.2.1 NB1 vocoder and HB1
folding; BSD provenance stays in the vendored math/decoder files and COPYING.
Measured on ATmega328P / classic AVR5 hardware MUL, GNU ABI, AVR GCC 7.3.0
with existing mixed Os/O2/O3, LTO/mcall-prologues/mrelax, avr8js 0.21.1.
The algorithm is portable C; existing multiplication/shift kernels keep an
explicit C fallback and require supported architecture plus ASM opt-in.

## Exploit the actual input domain before reducing precision

Xiph's `speex_rand(1)` emits only -2,-1,0,1,2. Keep its original 32-bit LCG:
reducing the RNG width would change the sequence. For signed high word r,
the literal output is `floor((r-floor(r/8)+8192)/16384)`. Exact transition
points are -28087, -9363, 9362, 28086, exhaustively checked over 65536 words.

Scale those five values once, preserving both original fixed-point floors.
For a frame-constant gain, precompute the five weighted results too. This
removes multiplications from the noise part of the inner vocoder loop.
Emit byte class indices rather than repeatedly transforming wide samples.

The 40 indices fit in the upper 40 bytes of the existing 80-byte excitation
buffer. Expand forward into signed16 words: after reading index at `40+i`,
the output writes `2*i` and `2*i+1`, never a future index. This works in both
byte orders; inputs/state must follow the documented private non-overlap
contract. No additional PCM frame or heap allocation is introduced.

## Store only state consumed by future output

The vocoder's previous wide innovation is used only after rounded >>14;
retain that exact signed16 word instead. Its previous pulse is consumed only
after constant Q15 multiplication by .3, so retain the weighted word.
Pitch phase remains 0..143: uint8 is sufficient (temporary phase <=183).
Pulse amplitude and both pulse weights are constants for the entire frame.
Carry the filter state in local words and write back after the frame.

The legal scales, 16384..115088100, produce noise words of magnitude <=14049.
Weighted pulse/noise state fits signed16. The mean-filter accumulator still
needs about 31 bits; retain int32 and its original low bits. Do not narrow
that feedback sum to 16/24 bits or change its rounding to save operations.

## Evidence and limits

The literal initial WB3.95 implementation checks 640 exact/reset voice frames
but costs about 416k cycles/frame, missing the 320k budget. Finite-domain
precomputation and exact word arithmetic reduce the same screen to about
267k, with unchanged PCM. The initial IRQ screen checks three 40-frame
streams, exact signed16/PWM, zero underruns and minimum queue 18.

These are screening results, not full-corpus/board admission. The target
[implementation and final evidence](../../Codecs/Speex/AVR/LOW_RATES.md) keep
the precise workload, binaries and memory figures. The mathematical proof
checks thresholds, original scaling equations, alias geometry and phase
bounds. The retained literal patch is a slow comparison, not a recommended
backend. New bitrate quality is separate from bit-exact decoder optimization.
