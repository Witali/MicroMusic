# Reuse related constant products in the paired QMF

This is a measured **isolated candidate** for the existing compact Speex
16-tap Q7 synthesis filter. Production integration and active PWM queue
admission remain separate work. Target: classic AVR5 / ATmega328P, hardware
MUL/MULS/MULSU, GNU AVR ABI, AVR GCC 7.3.0, avr8js 0.21.1. Arithmetic and
rounding stay exact; the filter coefficients, state and output format do not
change. Original project optimization; the existing Xiph Speex 1.2.1 BSD
provenance remains in the sources and `vendor/speex-1.2.1/COPYING`.

## One signed24 product can update two accumulators

The current paired loop reuses one signed16 history word for two output
accumulators. Two occurrences have coefficients 7 and -14. Compute `P=7*x`
once, add P to the first accumulator, shift P left once, and subtract it
from the second accumulator. Both accumulators were already initialized.

The high input byte is signed r24, the low byte is unsigned r21. The product
can occupy r20 (low), r30 (middle), r31 (high):

```asm
    ldi r20,7
    muls r20,r24
    movw r30,r0
    mulsu r20,r21
    mov r20,r0
    add r30,r1
    adc r31,r2              ; r2 is the existing zero register
```

The second product, `7*unsigned_low`, is nonnegative and below 32768, so the
general signed-coefficient MAC's sign-correction SBC is unnecessary. The
ADD/ADC above must propagate the carry from assembling the low-byte product.
Then three-byte ADD/ADC, LSL/ROL and SUB/SBC preserve signed24 arithmetic.
Neither the source input nor X is modified.

Scratch lifetime matters: both input pairs have already been read, and the
Z pointer is dead through the history MAC section. `movw r30,r22` restores
the output pointer immediately before WB_FINISH. r20 is already scratch.
The accumulators, live input/output pointers, zero register, loop count and
cursor limit remain intact. A later change that makes Z live in this section
must revisit this allocation.

## The optional -10/15 pair removes more MUL instructions

Two other occurrences have coefficients -10 and 15. Construct `P=10*x` with
the same positive-coefficient sequence, subtract P from the -10 accumulator,
add P to the 15 accumulator, arithmetic-shift P right once, and add it to
the 15 accumulator again. P is always even, including for negative x:
`P+(P>>1) == 15*x` exactly. Use ASR of the top byte followed by two RORs.

For all signed16 x, the intermediates 7*x, 14*x, 10*x and 15*x fit signed24.
The phase coefficient absolute sum is 236, so the accumulator and rounding
bias remain inside `236*32768+32 < 2^23`. Splitting a positive coefficient
15 into 10+5 does not increase that bound. No narrower approximations,
quantizer changes or discarded low bits are introduced.

The production C QMF source and architecture/explicit-ASM-enable selection
are untouched. The screen retains the unchanged portable C primitive in a
separate object and checks it against the same independent mathematical model.
No additional buffer, state byte, private call or stack save is needed.

## Measured isolated result

All variants use `-Os -mcall-prologues -mrelax -fwrapv
-fno-strict-aliasing -ffunction-sections -fdata-sections`, with LTO for the
mailbox/link. The unchanged explicit C primitive is a separate object with
its existing per-function optimization attribute.

| Recipe | Saving per forty-pair call | Byte MULs/call | Whole probe Flash |
| --- | ---: | ---: | ---: |
| Original | 0 cycles | 1280 | 2714 B |
| Share 7/-14 | 160 cycles | 1200 | 2706 B |
| Share both 7/-14 and -10/15 | 200 cycles | 1120 | 2710 B |

The time saving is identical on every paired block, including clipped and
aliasing cases. The second pair saves another 40 cycles/call for four bytes
relative to the first candidate; the combined candidate still saves four
bytes against the original isolated image. C primitive cycles and compiled
C object bytes are identical. Static SRAM is unchanged. Own ASM stack remains
18 B; the IRQ fixture peak remains 31 B.

Each recipe passes the original complete QMF corpus in both backends:
2244 blocks / 179520 output words per backend, 92 explicit rounding/clipping
boundary blocks, full signed16 input sweeps in both channels, alternating
permitted `high=out+40` alias, exact mirrored history, guards/read-only inputs,
and 2244 ASM callee-register/r1 return checks. These are channel sweeps,
not an exhaustive cross product of every possible input/history vector.

Separate compiled-MUL ISR proofs interrupt every executed instruction boundary
on eight ordinary/aliased, full-scale, random and preloaded-history vectors:

| Recipe | Boundary injections | Interrupted nonzero r1 |
| --- | ---: | ---: |
| Original | 75156 | 43723 |
| Share 7/-14 | 74516 | 43319 |
| Combined | 74836 | 43113 |

All 32 registers, SREG, PC and SP are restored at RETI. Both incoming T
values, arbitrary callee-register patterns and r1 are checked, with exact
whole-arena outputs/state/guards and identical interrupted instruction traces.
MUL counts above are observed directly in these ordinary calls. This proof
does not model hardware entry latency or establish production queue timing.

Four unchanged calls per WB frame would save 800 cycles and 640 byte MULs
with the combined recipe before caller/linker effects. **Whole-decoder saving
and production output admission have not been measured for this candidate.**
Physical hardware and analog output are not part of this screen.

## Reproduce and inspect the receipt

The [screen driver](../../Codecs/Speex/AVR/tests/screen_qmf_common_product.py)
pins and reconstructs the exact original and both candidate kernels in ignored
build directories. It derives a QMF-only mailbox from the existing kernel
fixture and runs its original oracle/alias/rounding cases, retaining per-block
cycle comparisons. The
[IRQ verifier](../../Codecs/Speex/AVR/tests/verify_qmf_common_product_irq.mjs)
provides the separate boundary-preemption and MUL-count proof.

```sh
python Codecs/Speex/AVR/tests/screen_qmf_common_product.py --avr-gcc avr-gcc --node node
# Audit executed, hash-verified images without repeating the simulations:
python Codecs/Speex/AVR/tests/screen_qmf_common_product.py --phase audit
```

The compact [receipt](../../Codecs/Speex/AVR/reports/qmf-common-product-screen.json)
binds normalized source hashes, exact firmware/C-object hashes and measured
results. Manufacturer headers and external tool executables use exact-byte
hashes. `--receipt <path>` saves a fresh audited receipt; generated images,
raw cycle arrays and logs remain under `build/qmf-common-product-screen/`.
