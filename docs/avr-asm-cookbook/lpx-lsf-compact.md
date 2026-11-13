# Smaller exact LSF to LPC conversion

Original MicroMusic work for ATtiny88 / AVR25 without MUL and ATmega328P /
AVR5 with MUL, GNU AVR ABI, AVR-GCC 7.3.0. The measured universal v9 recipe
uses `-Os -flto -mcall-prologues -mrelax -finline-small-functions`, SRAM512,
LPC segments 2, FIFO32/prefill24, 16 MHz / 8 kHz. Tiny software products use
unroll2 and the existing reserved-register ISR; Mega uses the ordinary C ISR.
Arithmetic selection and device/Flash access remain independent.

## Reuse the first polynomial coefficient

After the initial factor, P has coefficients
`[4096,4096+c,4096+c,4096]`; Q has
`[4096,-4096+c,4096-c,-4096]`. Form `first=unit+c` once, then store
`first` and either `first` or `-first`. Since `|c|<=8192`, the temporary is
in `[-12288,12288]` and fits signed16. Widen before negation at the word store.
This is shared fixed-point C++ in the SRAM512 path; it changes no product,
floor, cosine node, final clamp, workspace lifetime or serialized parameter.

## Narrow the high part only under a conversion bound

Each cosine factor is `(1,c/4096,1)` with `|c|<=8192`. For integer bound B,
`|floor(v*c/4096)|<=2B` when `|v|<=B`. Thus absolute coefficient bounds follow
convolution by `(1,2,1)`: after r quadratics they are bounded coefficientwise
by `4096*(1+z)^(2r+1)`. Before factors n4/n6/n8/n10 the maxima are
12288,40960,143360,516096. The first three remain on the direct-product path.

Before the last factor, `hi=trunc(v/16)` therefore has magnitude at most 32256.
Its signed16 representation is exact. Retain the existing 250000 threshold,
the signed remainder in [-15,15], and both separately floored products:

```c
floor(hi*c/256) + floor(rem*c/4096)
```

Use the existing signed16x16 backend for that high part on explicitly enabled
AVR25 ASM. The generic polynomial helper keeps its wider input contract and
the C/AVR5 fallback stays available. Selecting C on AVR still selects C.
No handwritten assembly, fake CPU macro or new build switch is introduced.
The floating synthesis branch excludes these fixed-point helpers entirely.

## Combined measurements

The first matched four universal controls give the following full linked
program sizes, excluding only their verified unchanged audio arrays:

| Target and backend | Before B | After B | Saving B | Decoder CPU plus complete IRQ |
| --- | ---: | ---: | ---: | --- |
| Tiny88 ASM | 5604–5605 | 5556–5557 | 48 | 4.82–5.20 fewer cycles/sample |
| Mega328P ASM | 5094–5095 | 5088–5089 | 6 | unchanged |
| Mega328P C | 4894–4895 | 4888–4889 | 6 | 0.023–0.025 fewer cycles/sample |

Tiny's peak observed stack falls 67→64 B, margin 11→14 B; static SRAM stays 433 B.
Mega stack/static SRAM stay unchanged. These are combined measurements:
adding standalone size savings would predict the wrong Tiny result.
Full playback, exact PWM, zero underruns, stack and output timing are checked
with IRQs active. Cycle figures are mean decoder CPU plus the complete IRQ,
excluding foreground queue work; they are not per-call worst-case bounds.
No physical board was measured.

## Independent checks and history

The retained `test_ring_polynomial_exact.py` compares the actual converter
against independent full scalar convolution and the original cosine ROM.
It covers 368640 conversions, all 256 ring cursors, 145 live history slots,
profiles 4/6/15 and LPC segments 1/2/4 under UBSan. Existing unrestricted
polynomial and frozen ordered-anchor checks remain separate.

The whole 181-record/306-segment corpus contains 15188029 samples: fixed native
PCM16 and PWM stay byte-identical to 0320c101. This is a fresh host comparison,
not another whole-corpus AVR timing run. A v9/SRAM512/LPC2 floating preprocessed
translation unit and complete host library also remain byte-identical.

Byte-offset recurrence, stage-specific guard removal, forced outlining and
output-loop variants were screened separately. Some smaller variants slowed
decoding; they remain rejected. In particular the combined byte-offset form
slows Mega ASM by about 0.07 cycles/sample and is not selected.

[Measurements and validation scopes](../../Codecs/LPX/research/lsf-compact-2026-11-10/README.md)
preserve the old receipts and introduce a separate source transition. Original
website catalogs/HEX remain bound to their released source; a current-source
rebuild comparison is not a silent rewrite of their historical timing values.

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/lsf-tiny --target tiny
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/lsf-mega --target mega
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests \
  -p test_ring_polynomial_exact.py
```

Add `--wsl Ubuntu` on Windows. `--case chego-2k` reproduces one matched
control. The verifier reconstructs the 0320c101 baseline from local Git,
freezes current sources, uses fresh ELF/IRQ runs, and rejects size, speed,
stack or exact-output regressions. All transformations are original project
code; no external implementation was adapted.

## Carry one old coefficient between iterations on AVR25

In the descending SRAM512 recurrence, the old coefficient at index
`j-2` becomes the multiply operand on the next iteration. Keep that
coefficient live across iterations and compute the product before loading
the other two terms. A byte offset advances by four with modulo-256 wrap
and aligned `memcpy` accesses. The AVR25 ASM selection uses this portable
C++ loop and the selectable C backend retains the original recurrence.
On ATtiny88 with AVR-GCC 7.3.0, AVR GCC ABI and `-Os -flto`, this saves
48 B of program Flash and 5 B of peak stack. All 22 loads preserve exact
PWM with IRQ, with up to 6.76 cycles saved per sample and no underruns.
[Measurements and verification](../../Codecs/LPX/research/tiny-lsf-neighbors-2026-11-13/README.md).

## Bounded hardware partial products on AVR5

For the direct polynomial branch, bounded signed24 times signed16
needs six byte products to produce the low 32 bits. Use the AVR5
`MUL` and `MULSU` instructions and restore `r1` before returning
through the AVR GCC ABI. In the split branch, the high part fits signed16
and both Q12-related floors stay independent. Select the assembly through
the supported AVR5 architecture and explicit ASM enable. The selectable
C backend provides the independent reference.

With AVR-GCC 7.3.0 at `-Os -flto`, the shared SRAM512 ring recurrence
and bounded product together save 40 B on all six universal ATmega328P
loads with IRQ. PWM matches exactly, the complete IRQ timing improves by
7.64–8.49 cycles per sample, and no queue underruns occur.
[Proof and measurements](../../Codecs/LPX/research/mega-lsf-wide-2026-11-13/README.md).

## Seed a shared descending loop for P and Q on AVR25

The SRAM512 universal v9 build on the no-MUL AVR25 backend prepares
two edge cases before the same descending loop. P reuses its old middle
for the new middle coefficient and the first multiply operand. Q retains
its fixed trailing unit as the first current coefficient in a register
and writes the new adjacent coefficient before entering the loop. The
trailing unit never needs a ring slot. Both paths use the same Q12
products and separately rounded wide-product terms.

P uses words 0 through 5 and Q uses 0 through 10. At four bytes per word
plus up to three bytes for alignment, the workspace fits inside 111
dead pitch-history bytes. Byte offsets wrap before aligned accesses.
The selectable C backend keeps its equivalent recurrence.

On ATtiny88 with AVR-GCC 7.3.0, the GNU AVR ABI and `-Os -flto`,
the converter and linked program each shrink by 90 B. The 22 v9 loads
preserve exact PWM and do not slow down in simavr with active IRQs.
Peak stack grows from 56 to 60 B with a measured minimum margin of 18 B.
[Measurements and reproduction](../../Codecs/LPX/research/tiny-v9-shared-pq-2026-11-13/README.md).

## Outline subframe preparation within the existing stack budget

The ATtiny88 standalone player enters `main` with IRQs masked and never
returns. Under the GNU AVR ABI, AVR-GCC's `OS_main` attribute omits saving
the caller's registers in this entry point. Ordinary decoder functions
and the ISR keep their existing register preservation.
See the [GCC AVR function attributes](https://gcc.gnu.org/onlinedocs/gcc-8.5.0/gcc/AVR-Function-Attributes.html).

With AVR-GCC 7.3.0 and `-Os -flto`, this recovers the stack needed to
outline parsing and interpolation at the 20-sample boundary. The
explicit AVR25 ASM universal v9 selection uses the outlined helper.
The C backend inlines the equivalent C++ implementation. On 22 simavr
loads with active IRQs, Flash drops by 32 B and peak stack by 6 B.
Every load speeds up and produces the same PWM bytes.
[Measurements and reproduction](../../Codecs/LPX/research/tiny-v9-subframe-2026-11-13/README.md).
