# Exact finite NB1 vocoder gain map

Baseline `4b45b0e4`; runtime `cce60d86`. Target ATmega328P / classic AVR5,
16 MHz, 2 KB SRAM, GNU ABI, AVR GCC 7.3.0, explicit ASM decoder and existing
mixed Os/O2/O3 with LTO, mcall-prologues and mrelax. Full before/after images
enable all lower rates and NB4. This stage changes NB1, used by NB2.15 and
compact WB3.95 (4.0 kbit/s in byte-aligned raw storage).

## Preserve both quantizers, compose their finite domain

The original frame preparation calculates two rounded transforms and a clamp:

```c
c = (2185L * (code << 6) + 16384) >> 15;
g = (24576L * (c - 13) + 8192) >> 14;
g = max(0, min(64, g));
```

There are exactly sixteen input codes. Retain c's full 0..64 domain, including
code15 ->64; submode8's separate coefficient clamp to63 does not apply here.
After both original rounded stages and the gain clamp, the exact outputs are:

```c
{0,0,0,0,6,12,20,26,32,38,45,51,57,63,64,64}
```

Store sixteen signed bytes in Flash using the existing table-placement/read
backend. They allocate no SRAM. A portable C arithmetic reference still uses
the narrowed coefficient and `(3*(c-13)+1)>>1`, retaining negative floor rounding
and both clamps. The selected lookup is also C; no handwritten arithmetic ASM
is added. Flash access remains independent of arithmetic selection, disabling
ASM still selects the portable decoder, and public APIs stay unchanged.

WB uses the direct read. Standalone NB retains a redundant `g<=64` clamp after
the read, exposing its range to the compiler. Both recipes are selected at
compile time by the existing WB profile flag and have identical gain values.

## Primitive and caller evidence

All sixteen codes pass five scalar paths: original, narrowed coefficient,
factored gain, direct lookup and bounded lookup, versus independent wide
arithmetic. LPM addresses are exactly table+code; each backend checks 80 GNU
saved-register/r1 returns. ASM-enabled/disabled scalar binaries are byte-identical.
Original wrappers take 298..301 cycles / 9 MULs, coefficient-only 162..165 / 6,
factored 33..35 / 2, direct lookup 11 / 0 and bounded lookup 14 / 0, including RET.
The direct inline read itself is seven cycles. Only isolated C controls execute;
the full C decoder is never run/timed.

The matched three-stream / 384-frame screen saves these cycles/frame:

| Variant | NB2.15 | WB3.95 |
| --- | ---: | ---: |
| Narrow coefficient | 138.000 | 138.000 |
| Factored arithmetic | 269.367 | 268.352 |
| Direct table | 153.823 | 293.802 |
| Table with bound | 309.823 | 290.802 |

The selected wrapper rebuilds byte-identically to each profile's fastest
recipe. NB's bound costs three scalar cycles, yet makes its full caller 156
cycles faster than direct lookup, with 14 B extra Flash. WB's direct read saves
three cycles and six bytes versus the bound. These are measured AVR-GCC caller
effects, not speed claims for other architectures or compilers.

## Complete-image admission

Before and after freshly pass each full 18-stream / 10627-frame corpus:
**42508 matched raw frames**, including resets. Each profile covers 6467
natural RU/EN frames, 4096 coverage and 64 padding frames. Every PCM word
matches the unchanged oracle. All sixteen codes execute; code15 occurs 256
times per full corpus.

| Bare decoder | NB2.15 before | NB2.15 map | WB3.95 before | WB3.95 map |
| --- | ---: | ---: | ---: | ---: |
| Speech cycles/frame | 102401.612 | 102092.481 | 222611.060 | 222317.916 |
| Decoder CPU at 16 MHz | 32.001% | 31.904% | 69.566% | 69.474% |
| Full-corpus max cycles | 103869 | 103557 | 225867 | 225571 |
| Flash | 17400 B | 17318 B | 25674 B | 25592 B |
| Static SRAM | 1104 B | 1104 B | 1284 B | 1284 B |
| Peak stack | 110 B | 110 B | 200 B | 200 B |
| Free SRAM at peak | 834 B | 834 B | 564 B | 564 B |

Means use exact per-frame sums. Command intervals include the mailbox, excluding
startup/reset/interrupts. Every NB frame improves 308..312 cycles, every WB
frame 292..296. Static SRAM and peak stack are unchanged; Flash shrinks 82 B
each. The before images include intervening shared-code/layout changes since
older WB3.95 notes, so comparisons use this fresh matched baseline.

| Paired continuous output | Frames/epoch | Extra work/frame | Min queue before/after | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB3.95 ready-RAM IRQ | 10627 | 25600 cycles (8%) | 30 / 30 | 410 B | 0 |
| WB3.95 ready-RAM IRQ | 10627 | 35200 cycles (11%) | 22 / 22 | 410 B | 0 |
| NB2.15 scheduled SPI | 6000 | 0 | 74 / 74 | 669 B | 0 |
| WB3.95 scheduled SPI | 3600 | 0 | 30 / 30 | 407 B | 0 |

The IRQ loads total **42508 matched frames**, exact continuous s16/PWM with
active timers/interrupts and no resets inside recordings. Their images shrink
26110 ->26028 B Flash, retaining 1425 B static SRAM / 213 B stack. SPI totals
**19200 frames / 4224000 samples**, exact s16/PWM. Each stream contains 36000
bytes, read with actual SPI/CS from 0xff80 across 64 KiB through the unchanged
shared W25Q128 model. NB SPI shrinks 17700 ->17618 B Flash with 1247 B static
SRAM / 132 B stack; WB SPI shrinks 26194 ->26112 with 1422 / 219. Intervals
stay within 1990..2010 cycles NB and 990..1010 WB. SPI adds no stress; ready
RAM excludes transport. These are ISA-simulator, not board/analog measurements.

Before/after mixed APIs each pass 1024 frames, padding/reset and 6144 NB /
7168 WB rejected calls. Both WB-enabled API images observe 206 NB1 preparations
each: 104 ->94 MULs/call, 21424 ->19364 total, including caller effects beyond
the isolated nine-product map. Each valid NB1 frame reads exactly one correct
gain-table byte; rejected/other modes read none. Noise-value, vocoder-quarter
and WB fold counters retain their original observations.

Six NB1-disabled images remain byte-identical: minimum NB8 kbit/s, NB11,
WB9.8, WB12.8 and NB8-only NB3.95/WB5.75. No fresh full all-feature other-mode
timing is claimed. NB1-only ASM images pass 384-frame screens, 12532 B NB /
19856 B WB. Their C images (13098/21306 B), full C SPI controls (21140/31396 B)
and the portable 21-source C11 export compile/link only. Compact WB retains
its established Q7/16-tap QMF. No amplitude threshold or quiet-speech suppression
is introduced; gain-zero codes retain all original noise, state and RNG work.

## Reproduce and continue

`reports/nb1-gain-admission.json` binds sources, parent admission, unit/variant
reports and firmware hashes. Parent sources are checked against their full
178-file admission; old reports remain intact. Traces, firmware, PCM, logs and
model/link artifacts stay ignored; `--corpus` rechecks full source/oracle hashes.
Run screening before the final builder; it restores the incoming controller.

```sh
python Codecs/Speex/AVR/tests/build_nb1_gain.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_nb1_gain.mjs Codecs/Speex/AVR/build/nb1-gain-unit/asm
node Codecs/Speex/AVR/tests/verify_nb1_gain.mjs Codecs/Speex/AVR/build/nb1-gain-unit/c
python Codecs/Speex/AVR/tests/screen_nb1_gain.py --avr-gcc avr-gcc --node node --baseline-root <parent-codec-root> --corpus <low-corpus>
python Codecs/Speex/AVR/tests/build_nb1_gain_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --low-corpus <low-corpus> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_nb1_gain_admission.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat irq8, irq11 and transport-api.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_nb1_gain.py --corpus <low-corpus>
```

Unmeasured candidates: gain-zero preparation (1965/6467 NB, 1977/6467 WB speech
frames), complementary pulse/feedback coefficients and old ASM section
ownership. A gain-zero shortcut must retain noise, prior pulse, state and all
160 RNG transitions. See the cookbook for identities and their verification
scope. Existing Xiph BSD provenance remains; map/observer adaptations are project work.
