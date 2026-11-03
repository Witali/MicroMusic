# Split a bounded constant MAC into two word accumulators

Measured candidate for the compact Speex Q7/16-tap QMF on ATmega328P,
classic AVR5 with MUL/MULS/MULSU, GNU AVR ABI, AVR GCC 7.3.0 and avr8js
0.21.1. The complete WB3.95/WB12.8 screens below preserve PCM and production
IRQ output exactly. Full-corpus and transport admission remain separate.
The existing explicitly selectable C fallback and architecture/ASM-enable
selection are unchanged. Xiph Speex 1.2.1 BSD provenance remains with the
sources; the split arithmetic, allocation and proofs are original project work.

## Choose the bias from the coefficient domain

For a signed16 input, write `x = 256*hi + lo`, with signed8 hi and unsigned8
lo. Each eight-coefficient QMF phase has positive coefficient sum 182 and
negative magnitude 54. Therefore:

```text
H0 = sum(coefficient * hi)       lies in [-30154,30026]
H  = H0 - 54                    lies in [-30208,29972]
L  = 13824 + sum(coefficient*lo) lies in [54,60234]
sum(coefficient*x) = (H + (L>>8))*256 + (L&255)
```

Every partial coefficient subset also fits these bounds. H is signed16; L
is unsigned16 and never underflows or overflows. Each individual byte product
fits signed16. A normal MAC needs two MULs and four ADD/ADCs, with no separate
signed24 sign correction or propagation into a third byte. Initialize H with
the first signed-high product minus 54 and L with the first low product plus
54 in its high byte. One shared `ldi r30,54` supplies the four initial biases.

Before the original WB_FINISH, add L's high byte into H with ADD/ADC. Feed
L.low, H.low and H.high into the unchanged signed24 finish. Its rounding bias,
Q6 shift and saturation to +/-32767 remain unchanged. The accumulated value
still fits `236*32768+32 < 2^23`. Recalculate all bounds for different filters;
this is not a generic narrowing rule for arbitrary coefficients or orders.

The 7/-14 common product remains useful in each half separately. The -10/15
sharing recipe is slower than two independent split MACs and is expanded.
Consequently the new path executes more MULs than the previous combined
common-product kernel, while measured total execution is faster.

## Allocate sixteen accumulator bytes

Each group holds L.low, L.high, H.low, H.high: r4..7, r8..11, r12..15 and
r16..19. The fourth group conflicts with the live low/high input pointers.
After both WB_INPUT operations, spill those four pointer bytes until all four
outputs are finished. Source input r24:r21 and X remain unchanged through the
MAC section. The saved oldest history words are consumed in their original
order. No private subroutine, state field or static buffer is added.

Two measured choices retain the exact arithmetic:

- **Stack spill:** four PUSHes and four POPs per paired iteration; four more
  bytes of own ASM stack. This is the faster and smaller isolated variant.
- **Dead mirror record:** wrap Y first, then set X=Y+32. The active history
  window is `[Y,Y+32)`; Y+32..35 is outside it and can hold the pointers.
  At wrap, reading the original copy instead of its mirror is equivalent.
  The next insertion restores the corrupted duplicate before using it. After
  the final iteration, copy Y..Y+3 back to Y+32..35 so all 64 public state bytes
  match the reference at return. That final repair costs 16 cycles per call.

Wrapping Y before this scratch write is essential to keep it inside the
64-byte state. The scalar geometry proof covers all 256 base low bytes and
1024 cursor windows, including low-byte carry. Existing input/output/state
non-overlap rules still apply. The permitted high=out+40 layout is preserved.

## Isolated arithmetic and IRQ results

The baseline is the already combined common-product kernel. All recipes use
the existing pinned `-Os -mcall-prologues -mrelax -fwrapv
-fno-strict-aliasing` fixture flags and unchanged separate C filter object.

| Recipe | Saving/call | MULs/call | Probe Flash | Own ASM stack |
| --- | ---: | ---: | ---: | ---: |
| Combined common-product baseline | 0 cycles | 1120 | 2710 B | 18 B |
| Split, stack spill | 500 cycles | 1200 | 2636 B | 22 B |
| Split, mirror spill | 484 cycles | 1200 | 2652 B | 18 B |

Each saving holds on every one of the original 2244 blocks / 179520 output
words per backend. The full signed16 channel sweeps, 92 rounding/clipping
boundary blocks, alternating alias, mirrored state, input/output guards and
2244 ASM register/r1 returns pass. The explicit C object is byte-identical and
its timings are unchanged. A separate scalar proof checks 524288 byte
products and all 512 partial coefficient subsets.

The stack/mirror IRQ probes pass 68916/68980 instruction-boundary injections,
including 39444/39476 interrupted nonzero-r1 states. All 32 registers, SREG,
PC and SP are restored; arbitrary callee patterns, both incoming T states,
whole arena/alias/state equality and identical instruction traces pass. Own
IRQ fixture peaks are 35/31 B. The baseline IRQ proof is reused only after
the newly built control binary matches the previously executed image exactly.

## Complete WB screens

All twelve complete images use the same frozen `hb-finite-speed` sources,
compiler and flags. The four baseline decoder/IRQ controls rebuild identically.
For candidates, only the compiler argument naming `wb_qmf.S` changes; the
production tree and prepared source cache are verified unchanged.

WB3.95 covers 18 recordings, each capped at 64 frames: 1152 sequential frames.
WB12.8 covers the first 64 frames of the retained long recording. Raw PCM and
reset checks pass. The stack variant saves exactly 2000 cycles on every frame;
mirror saves 1936. Complete raw means are:

| Profile | Baseline | Stack | Mirror |
| --- | ---: | ---: | ---: |
| WB3.95 | 217078.219 cycles | 215078.219 | 215142.219 |
| WB12.8 | 231971.188 cycles | 229971.188 | 230035.188 |

Raw images shrink 26164 -> 26090 B (stack) or 26106 B (mirror). Static SRAM
stays 1284/1306 B for the two mailbox widths. Raw whole-image stack peaks
change 198/197 -> 199/199 B with stack spill; mirror retains 198/197 B.

Both complete production IRQ/queue screens also pass with exact s16/PWM,
zero underruns and **8% extra foreground work**:

| Profile / recipe | IRQ image Flash | Peak stack | Free SRAM | Minimum queue |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 baseline | 26600 B | 211 B | 412 B | 31 |
| WB3.95 stack | 26526 B | 212 B | 411 B | 31 |
| WB3.95 mirror | 26542 B | 211 B | 412 B | 31 |
| WB12.8 baseline | 26600 B | 210 B | 391 B | 8 |
| WB12.8 stack | 26526 B | 212 B | 389 B | 9 |
| WB12.8 mirror | 26542 B | 210 B | 391 B | 8 |

IRQ static SRAM remains 1425/1447 B. Output intervals remain within
995..1005 cycles. These screens support selecting the faster stack variant
for the next full admission: its four-byte own-stack increase raises the
complete maximum by only one/two bytes. Results do not establish other
profiles, full recordings, transport latency or physical-board behavior.

## Reproduce

The [driver](../../Codecs/Speex/AVR/tests/screen_qmf_split_accum.py) pins and
reconstructs both candidates without production writes. It reuses the existing
QMF oracle and IRQ probes, and preserves the full-image compiler override.
The complete screen needs the retained `build/hb-finite-speed` inputs, oracles,
baseline reports and prepared source cache.

```sh
python Codecs/Speex/AVR/tests/screen_qmf_split_accum.py --avr-gcc avr-gcc --node node
# Verify existing evidence without repeating completed measurements:
python Codecs/Speex/AVR/tests/screen_qmf_split_accum.py --phase audit
```

The [receipt](../../Codecs/Speex/AVR/reports/qmf-split-accum-screen.json) binds
LF-normalized source hashes, exact tool/header/binary/C-object hashes,
screen input/oracle hashes and measured resources. Generated firmware, raw
timings and logs remain under `build/qmf-split-accum-screen/`. The production
implementation and shared cookbook index are left to the integration stage.
