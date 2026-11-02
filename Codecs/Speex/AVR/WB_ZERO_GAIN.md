# Exact NB1 zero-gain preparation

Baseline `1cdda26c`; runtime `72e32ba4`. Target ATmega328P / classic AVR5, 16 MHz / 2 KB SRAM,
GNU ABI, AVR GCC 7.3.0 with the existing mixed Os/O2/O3, LTO,
mcall-prologues and mrelax. This stage affects NB2.15 and compact WB3.95.
Full matched images enable all lower rates and NB4. No new handwritten ASM,
table, context field or RAM buffer is introduced; preparation remains C with
the existing explicitly selectable ASM/C decoder and independent memory backend.

## Derivation and state contract

The original finite gain is zero for codes 0..3. Therefore amplitude, both new
pulses, previous-noise gain and initial previous-noise product are exactly zero.
Skip their square root/products, but retain the old persistent pulse. The
current noise still uses gain 32767. For every noise-table word n,

```c
floor(32767*n/32768) == n - (n>0);
```

This specialization excludes -32768: the original five-value noise table has
scale 0..121000000 and outputs -14771..14771. The general signed16 identity
adds `(n==INT16_MIN)` and is retained alongside the bounded helper. Both are
exhaustively checked on the target ISA. Negative floor rounding is unchanged.

Zero pulse gain is not silence. Preserve current noise, all previous[] zero
stores, the original high-band prefold, prior pulse, mean, phase, previous raw
noise, all 160 RNG steps, quarter states and original compact QMF. Preparation
must not change any persistent vocoder state or seed.

## Choosing the complete caller

The 384-frame screen compares the original, root/product guard only, per-word
branch, duplicated branch loops and a shared WB prefold loop. The selected
shared loop saves 78 B Flash versus duplication, costing 3.24 mean cycles/frame
on that WB screen. It is eleven cycles faster on zero-gain frames; nonzero
frames take 9..17 more cycles than duplication. NB versions are byte-identical.
Do not substitute this screen's averages for natural-speech measurements.

## Complete-image results

Fresh after runs cover **21254 raw frames**, two **10627-frame WB IRQ** runs
at +8%/+11% extra work and **9600 continuous SPI frames**. Each raw corpus has
18 streams: 6467 natural Russian/English frames, 4096 coverage and 64 padding.
Every PCM word matches the unchanged oracle. Before reports, images and raw
traces are reused from the source/hash-verified parent's completed evidence;
before mixed APIs are freshly reobserved to classify preparation by gain.

| Bare decoder | NB2.15 before | NB2.15 after | WB3.95 before | WB3.95 after |
| --- | ---: | ---: | ---: | ---: |
| Speech cycles/frame | 102092.481 | 101730.884 | 222317.916 | 222041.839 |
| Decoder CPU at 16 MHz | 31.904% | 31.791% | 69.474% | 69.388% |
| Full-corpus maximum cycles | 103557 | 103324 | 225571 | 225433 |
| Flash | 17318 B | 17418 B | 25592 B | 25724 B |
| Static SRAM | 1104 B | 1104 B | 1284 B | 1284 B |
| Peak stack | 110 B | 112 B | 200 B | 200 B |
| Free SRAM at peak | 834 B | 832 B | 564 B | 564 B |

Means use exact per-frame sums, excluding reset/startup/interrupts. Zero-gain
frames save 916..967 cycles NB / 876..927 WB. Nonzero NB saves 101..106;
nonzero WB changes -1..+4 cycles, already included in the speech mean. Natural
speech contains 1965 NB / 1977 WB zero-gain frames. The speed improvement costs
100/132 B bare Flash; NB stack grows two bytes. Static SRAM is unchanged.

Both full WB IRQ loads preserve exact s16/PWM and zero underruns. Flash is
26160 B, static SRAM 1425 B, peak stack 213 B, free 410 B; minimum queues remain
30 (+8%) and 22 (+11%). Actual scheduled SPI/CS reads 36000 bytes per stream
from 0xff80 across 64 KiB through the unchanged shared W25Q128 model. NB 6000 /
WB 3600 frames retain exact s16/PWM, no underruns and minimum queues 74/30.
SPI images use 17720/26244 B Flash, 1247/1422 B static SRAM, 134/219 B peak stack,
667/407 B free SRAM. Timer intervals are 1995..2005 NB / 995..1005 WB cycles.
SPI has no extra foreground stress; ready-RAM IRQ excludes transport latency.

Both mixed APIs pass 1024 frames, padding/reset and 6144/7168 rejected calls.
Each observes 206 NB1 preparations: 49 zero-gain calls use 16 rather than 94 MULs;
157 nonzero calls retain 94, total 19364 -> 15542. The remaining 16 MULs are the
four WB prefolds; both API fixtures include WB support. Gain-table reads,
noise generation, quarter synthesis and fold counters remain exact.

The independent state fixture checks 1024 mixed frames / 820 NB1 quarters,
49 zero-gain frames and 21 transitions in each direction. Natural mixed input
contains no zero frame starting with a nonzero prior pulse. Four explicitly
injected persistent states cover that case for codes 0..3, including both signs
and extreme means: original excitation, all quarter states, seed, fold and
guards are exact. These four frames do not claim an independent PCM oracle.

Isolated original/general/bounded unity primitives cover 196607 GNU saved-
register/r1 returns per backend. ASM-enable1/0 scalar images are byte-identical.
General and bounded helpers use 0 MULs, 23..24 / 12..13 cycles including RET;
the isolated C original uses 4 MULs, 147..150 cycles. This is not a comparison
against production inline ASM Q15 timing. Full C decoders never execute.

Six NB1-disabled images stay byte-identical. NB1-only ASM screens pass 384
frames each (12632/19988 B). C feature images 13192/21422 B, full C SPI controls
21234/31512 B and the portable 21-source C11 export compile/link only.
All runtime evidence is ISA simulation, not physical-board/analog measurement.

## Reproduction and next candidates

`reports/nb1-zero-admission.json` binds 194 sources, parent admission, firmware
and retained reports. Prior evidence is unchanged. Generated binaries, traces,
PCM and logs remain ignored. Run isolated unity tests and layout screens before
the final builder; screening restores the incoming controller source.

```sh
python Codecs/Speex/AVR/tests/build_nb1_unity.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_nb1_unity.mjs <unit-asm-dir>
node Codecs/Speex/AVR/tests/verify_nb1_unity.mjs <unit-c-dir>
python Codecs/Speex/AVR/tests/screen_nb1_zero_gain.py --avr-gcc avr-gcc --node node --baseline-root <parent-codec-root> --baseline-images <parent-after-dir> --corpus <low-corpus>
python Codecs/Speex/AVR/tests/build_nb1_zero_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --baseline-images <parent-after-dir> --low-corpus <low-corpus> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_nb1_zero_admission.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat irq8, irq11 and transport-api; the state verifier also includes injected cases.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <export-dir>
python Codecs/Speex/AVR/tests/audit_nb1_zero_gain.py --corpus <low-corpus>
```

Unmeasured candidates remain: remove zero pulse/previous-array work in the
quarter synthesis loop, use exact complementary pulse/feedback coefficients,
and pair opposite noise values in prefold. None is admitted by this stage.
Retain pinned Xiph Speex 1.2.1 BSD provenance; identities/adaptations are project work.
