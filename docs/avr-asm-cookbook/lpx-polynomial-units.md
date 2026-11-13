# LPX: exact trailing units in the LSF polynomial

Applicable measured target: ATmega328P / AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0,
16 MHz / 8 kHz, unroll 1/tuning 0 and `-Os -flto -mcall-prologues -mrelax`.
This is an original portable C++ algorithm simplification; it adds no assembly,
changes no backend selection, and uses existing manufacturer headers unchanged.

The P/Q LSF polynomials start with trailing coefficients +4096/-4096. Each
factor promotes that unit to the next trailing position before overwriting the
old terms. Thus the edge `floor(p[n-1]*c/4096)` is exactly +c or -c. A signed32
conditional negation replaces the general multiplication and its range paths.
Retain every other product's original independent floor, the wide-product guard,
coefficient truncation/clamps and the existing selectable C/ASM backends.

Measured on eight fixed complete clip images: Flash unchanged on six and 2 B
smaller on two five-reset images, SRAM unchanged. Two real 64000-sample profiles,
normal/+100 IRQ, give 2.35..2.76% lower IRQ-inclusive decode totals, exact full
PWM, zero underruns and observed after-ready stack margin 887->889 B. This is
simulator evidence for those images, not a portable speedup, board or startup
stack guarantee. 564288 compiled factor comparisons plus frozen and ordered LPC
oracles validate the same reference output.

P-only reciprocal folding was also assembled and coefficient-verified, but grew
Flash 70..160 B depending on output strategy and was rejected. Mathematical Q
antisymmetry is insufficient under per-product negative floor rounding. Do not
fold Q, or trade precision to mirror it, under an exact-output claim.

[Source, hashes, measured constraints and rejected patches](../../Codecs/LPX/research/decoder-polynomial-2026-10-28/README.md).

The same study also retains a rejected bounded two-half pulse insertion: it
saves 124 B in two five-reset images but grows six single-reset images by 26 B.
Caller-specific size effects require actual complete images; the existing loop
remains selected.

## Half-P recurrence admitted for universal AVR25 playback

The later universal Tiny88 profile reinvests software-multiply Flash savings
in P-only symmetry. This is a new measured admission, distinct from the earlier
AVR5 size rejection. The fixed-header ROM recipe keeps the former code size.

P starts with (1+z); equal mirrored inputs receive exactly the same separately
rounded product, including the wide-product guard. Retain coefficients0..k for
degree2k+1. Before the next quadratic factor, seed the new middle coefficient
from the old middle; then run the unchanged descending recurrence on that half.
At final degree11, read P[j] as P[11-j] for j>5. Q still uses all coefficients:
negative floors prevent exact antisymmetry. This is portable C++ and applies
with either selected arithmetic backend; the standard-memory full recurrence
remains an independent output oracle.

Screened on chego P4/v9 with AVR-GCC 7.3, unroll2, FIFO44 and active IRQs, this
change spent90 program bytes and reduced the active exclusive CPU mean from
1589.498 to1571.128 cycles/sample, with exact PWM and unchanged 445 B static
SRAM/60 B stack. Subsequent combined arithmetic changes fit below the original
program size on all 14 streams. See the
[current admission](lpx-universal-tiny88.md#exact-work-reduction-toward-1500-cyclessample-2026-11-10)
for the complete measured profile and target shortfall; do not extrapolate
this single ablation to AVR5 or other compiler recipes.
