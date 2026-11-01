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

## Complete admission

The new WB3.95 image passes all **10627 sequential frames** and 18 reset checks,
including 6467 natural Russian/English frames, 4096 coverage frames and 64
padding frames. The NB-only image is byte-identical to the preceding admitted
NB2.15 image, so its 10627-frame evidence is retained without an unnecessary
decoder rerun. Both mixed-mode API families pass 1024 frames and the existing
bad-length/null/header/padding checks with exact PCM and reset replay.

On the same 16 natural recordings, speech mean decreases 256395.662 ->
241931.037 cycles/frame: **5.64% faster than the seven-MUL stage**. Decoder CPU
falls **80.12% -> 75.60%**. Relative to the implementation before both changes,
the improvement is **9.62%**, from 83.65% CPU. Across all 10627 WB frames,
mean is 242991.238 and maximum 245212 cycles, excluding interrupts/output.

| Continuous output | Frames | Extra work/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB3.95, ready RAM | 10627 | 0 | 30 | 411 B | 0 |
| WB3.95, ready RAM | 10627 | 25600 cycles (8%) | 2 | 411 B | 0 |
| WB3.95, actual SPI | 3600 | 0 | 29 | 412 B | 0 |
| WB12.8, actual SPI | 2200 | 0 | 30 | 386 B | 0 |

The two ready-RAM runs retain production timers/IRQ/queue code and compare all
s16/PWM samples with unbroken decoder history. The preceding +8% screen had
failed; this stage now passes the complete corpus at that load. The minimum
queue of two is the observed simulator result, not a physical-board margin.

Separate SPI runs read 36000 and 70400 compressed bytes from address `0xff80`,
crossing 64 KiB boundaries. The WB3.95 production image compares the entire
PWM stream; the higher-rate observation image compares every s16 block too.
Both invoke the shared C W25Q128 model on actual scheduled AVR SPI completions,
with interrupts active. No extra foreground load is added to the SPI tests.
WB3.95 SPI Flash shrinks 25316 -> 25232 B; static SRAM 1422 -> 1418 B and
peak stack 229 -> 218 B leave 412 B free. No physical/analog test is claimed.

Four lower-rate-disabled minimal ASM images remain byte-identical. AVR C
fallback images compile/link (NB11 21098 B, WB3.95 30710 B); the exported C11
package compiles/links without `.S` dependencies. The C decoder is not executed
or timed. No public library interface changes.

`reports/noise-cache-*.json` binds source, firmware, corpus, pipeline and output
evidence. The current audit overlays six changed source files on the historical
seven-MUL admission; older audits stay pinned to their source baseline. Five
final decoder/IRQ/SPI images rebuild byte-identically.

```sh
python Codecs/Speex/AVR/tests/build_noise_cache.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_noise_cache.mjs Codecs/Speex/AVR/build/noise-cache-unit <mixed-WB-corpus>
python Codecs/Speex/AVR/tests/audit_noise_cache.py --corpus <lower-corpus>
python Codecs/Speex/AVR/tests/audit_noise_cache.py --corpus <lower-corpus> --avr-gcc avr-gcc --spi-stream <long-WB3.95-file> --higher-stream <long-WB12.8-file>
```

`build_noise_admission.py` prepares the main test images using the existing
corpus/IRQ/API/SPI verifiers; its input is the prepared `spi-corpus` directory
layout documented in the previous stage. Higher-rate SPI is built by
`build_spi_player.py --wideband --enable-nb4 --capture-pcm` with the same flags.

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
