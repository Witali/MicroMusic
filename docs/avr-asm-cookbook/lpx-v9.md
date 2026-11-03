# LPX v9: simplify wire decoding without expanding compressed data

Original MicroMusic work for ATtiny88 / AVR25 without MUL, GNU AVR ABI,
AVR-GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`, the universal FIFO44 recipe,
software product unroll2 and explicitly enabled arithmetic/ISR ASM. Portable
C remains separately selectable, including on AVR. These are simavr 1.6
measurements at requested 16 MHz / 8 kHz, not physical-board measurements.

The [wire specification](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/LPX9_FORMAT.md)
defines a 13-byte header with all variable recording parameters. Spectral
packing and DSP stay shared with v5. The new representation:

- Removes nine header bytes by using a short version identifier, the existing
  sample-count bound and format-defined packet geometry.
- Omits seven lag bits when pitch gain is zero. The product is exactly zero
  regardless of the lag/history, including separate signed rounding.
- Omits final packets that playback never reads, retaining every field that
  the current 40-sample pulse reader consumes, even for a shorter sample tail.
- Reindexes a P6 pulse pair into two low coordinate bits per position and a
  5x5 high-coordinate index. A25-byte Flash table replaces division by 20 and
  its software constant products, with the same nine-bit data cost.
- Reads each P4 position/sign as one 5-bit field instead of two reader calls.

For every valid input v5 stream, conversion never adds payload bits and removes
nine header bytes. No acoustic search, new codebook or coefficient quantization
is involved. PCM16/PWM remains exact. Ignored zero-gain lag values and unplayed
padding are not preserved as original bytes when repacking back to v5.

## Matched complete playback

[Source-bound measurements](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/v9-measurements.json)
compare eight complete public P4/P6 phrases and six synthetic controls with
changing/clustered spectra, lag 18/145, extras and boundary filter coefficients.
Each v9 full playback is checked against portable C and the actual v5 output.

| Quantity | V5 | V9 |
| --- | ---: | ---: |
| Universal program excluding verified audio | 5487..5488 B | 5424..5425 B |
| Complete image including each test stream | 5958..7386 B | 5874..7306 B |
| Static SRAM / peak observed stack | 447 / 60 B | 447 / 60 B |
| Complete ISR, hardware entry through RETI | 42 cycles | 42 cycles |
| Underruns | 0 | 0 |

The program saves 62..64 B, in addition to smaller audio files. On the four
public phrases, compressed data shrinks as follows:

| Phrase | P4 data bytes, v5 to v9 | P6 data bytes, v5 to v9 |
| --- | ---: | ---: |
| Chego | 536 to 522 | 791 to 776 |
| Otvechaesh | 470 to 450 | 692 to 671 |
| Vinni | 1243 to 1200 | 1862 to 1820 |
| Bread | 1008 to 996 | 1899 to 1881 |

Thus these files save 12..43 B (about 0.95..4.26%). All fourteen IRQ-active mean
decode costs improve, by about 0.3..0.5%; exact before/after means, maxima and
queue minima are in the receipt. PCM/PWM bytes stay identical. SRAM, observed
stack, the four-byte conservative margin and the 42-cycle ISR are preserved.
The admission remains bounded to these standalone workloads; extra application
state/IRQs and other streams need their own timing/stack check.

## Cold parser placement matters

With the shorter header, GCC/LTO partially inlined `begin()` into `main()`:
the screened main grew from 2728 to 2984 B and collided with the 512-byte stack
boundary on the first public P4 run. Marking the v9 `begin()` non-inlined keeps
cold setup out of playback's persistent frame and restores the measured 60-byte
stack. Scope this attribute to v9. Applying it to the old fixed-header player
grew some images and stack frames; the old recipe is retained.

The same compiled portable v9 decoder passes all 400 valid pulse pairs and all
112 invalid codes, 60 combinations of recording/filter settings, count 64000,
partial tails, ROM/callback switching, both memory profiles, both cursor modes
and both remaining-count strategies. An additional 16,000-sample full AVR playback
checks all 400 valid pairs with IRQs, exact v5 PWM and zero underruns.
Read to the final false `next()` and
check `error()` to validate exhaustion, including partial sample tails.

A separate data-only screening of globally selectable Rice parameters found
only 0..2 bytes of potential spectral savings on these public streams. No
runtime state/decoder machinery for that idea was added; speed/code-size
benefits were not measured. Directly storing LPC anchors was not adopted:
removing conversion alone is insufficient without proving smaller audio data.

Reproduce using the commands in the wire specification. Old v5/v8 data and
published speech recipes remain on their existing paths; selecting v9 is a
format choice, independent of CPU arithmetic and hardware memory access.

An unassembled table-free follow-up is `q=(h-(h>>2)+(h>=20))>>2` for
`0 <= h <= 24`, followed by remainder `h-5*q`. The identity was exhaustively
checked on its 25 inputs in host Python. AVR code size, stack and cycle cost
have not been measured; the admitted reader still uses the 25-byte table.
