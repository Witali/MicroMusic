# Reuse exact low-band noise in HB1

Baseline: `53eb8644`, the admitted seven-MUL RNG. Target remains ATmega328P,
16 MHz / 2 KB SRAM, explicit AVR ASM. Arithmetic width, random sequence,
rounding, packet formats and the compact Q7/16-tap QMF are unchanged.

NB1 already generates the 160 classes and five scaled words needed by HB1.
Instead of regenerating them, retain them in the dead prefix of the existing
excitation history. No new array or heap allocation is introduced. Remove the
four-byte shadow WB seed and its private getter; the real NB seed still advances
exactly 160 times per NB1 frame. Other submodes do not use this cache.

## Lifetime and boundaries

The restricted decoder has 145 prior excitation words plus 160 current words.
Its direct IIR input retains the original 40-sample delay:

| Bytes relative to excitation history | Owner during NB1 synthesis |
| --- | --- |
| 0..159 | Cached noise classes, one byte each |
| 160..169 | Five exact scaled signed16 noise words |
| 170..209 | Unused gap; canaries in the observation test |
| 210..289 | Previous-frame delayed input, preserved |
| 290..609 | Current 160-word excitation, preserved after construction |
| 320..609 | Source of the next frame's 145-word history move |

NB1 vocoder construction does not read adaptive pitch history. The current
frame begins at word 145; its earliest IIR read is word 105 (byte 210).
The next history move starts at word 160 (byte 320), beyond the cache.
Compile-time assertions bind the fixed frame geometry and both live boundaries.
The WB callback reads the bank synchronously before the next frame. The
existing static decoder is non-reentrant; this change adds no reentrancy.

Narrowband builds without WB keep the previous in-place forty-class expansion.
The cache is common C code on every architecture; C/ASM arithmetic selection
remains separate, with the same explicitly selectable C fallback.

## Initial measured screen

Same three 128-frame streams as the preceding speed stage: constructed
coverage, `en_letter_a`, `ru_slutskaya_a`. AVR GCC 7.3.0, existing Os/O2/O3,
LTO/mcall-prologues/mrelax, avr8js 0.21.1. Every PCM word and reset matches
the independent established compact-WB oracle.

| WB3.95 | Seven-MUL baseline | Reused noise |
| --- | ---: | ---: |
| Mean cycles/frame | 257745.846 | 243283.622 |
| Flash bytes | 24804 | 24726 |
| Static SRAM bytes | 1288 | 1284 |
| Peak stack bytes | 210 | 199 |
| Free SRAM at peak | 550 | 565 |

The screen improves another **5.61%** with smaller Flash and RAM. RNG draws
fall 320 -> 160 per WB3.95 frame, and five-word scaling runs fall five -> one.
With the seven-product kernel, RNG hardware multiplies fall 2240 -> 1120 per
frame, versus 3200 before both stages. These counts concern the RNG, not all
decoder multiplication. This is an exact speed/memory change, not a quality tradeoff.

The cache observation application processes 1024 mixed-mode frames and compares
every s16 block. For 205 NB1 frames it checks the original random equation and
word-scaling formula independently, 820 cached expansions, and actual call
counts: one values table and four 40-class generations per frame. Forty guard
bytes, the delayed old history, cache immutability, output guards, the seed and
reset clearing all pass. Caller addresses and geometry come from compiled
headers/offsetof, rather than guessed structure offsets.

Complete corpus, active-IRQ/SPI and portable-export admission follow separately.
The independent C decoder runtime suite remains excluded.

## Next speed candidates

The fresh profile still attributes substantial work to two areas:

- The vocoder mean update uses two products with coefficients 26214 and 6554,
  whose sum is 32768. Exact algebra gives `old + round(6554*(value-old)/32768)`.
  The difference needs 17 signed bits; a wrapped signed16 difference requires
  a correction of +/-13108 on overflow. A single-product implementation must
  prove every wrap/rounding boundary and beat its added bookkeeping on AVR.
- The HB1 gain division uses a positive table value <=904448 and a validated
  denominator 1..32767. Including rounding, its numerator is <2^20; an unsigned
  16-bit remainder is sufficient. Dividing the high nibble first can leave
  only sixteen quotient iterations, instead of generic 32-bit division. Keep
  the original C formula and exhaustively check all table/divisor pairs.

These are unimplemented opportunities, not admitted speedups. In particular,
leave the separate LPC-response `PDIV32` untouched: its rounding macro casts
the divisor to signed16 even though the final division uses a 32-bit divisor.
