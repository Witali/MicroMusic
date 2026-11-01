# Exact bounded HB1 gain division

Baseline: `3a0462fb`. Target: ATmega328P / AVR5, GNU ABI, AVR GCC 7.3.0,
16 MHz, explicit `SPEEX_NB3_ENABLE_ASM=1`. Only HB1's second gain division
changes; all five supported compact WB profiles share it. The separate
LPC-response division retains its original signed16 rounding cast.

The table energy is nonnegative and at most 904448. The validated divisor is
1..32767, so the rounded numerator is at most 920831, below 2^20. Divide its
high word first, then process the sixteen low bits. Before each low-bit step
the remainder is less than the divisor; doubling it and adding a bit is at
most 65533. Thus a 16-bit remainder is exact. The high-word quotient is at
most thirteen. No reciprocal approximation or rounding change is involved.

`src/wb_gain_div.S` uses 62 bytes, call-clobbered registers and no local stack,
memory accesses or interrupt masking. It preserves r1 and every callee-saved
register. `src/wb_gain_div.h` retains the original C expression, explicitly
callable even in ASM builds. Architecture identification and the separate ASM
enable select the existing backend; C is the default, including on AVR.

The isolated real-ABI test checks **1,049,060** cases: every one of the 32
table energies against all 32767 positive divisors, plus 516 boundary cases.
AVR C and ASM agree with independent BigInt arithmetic. Arbitrary callee-saved
patterns, r1, readonly inputs and stack boundaries pass on every ASM return.
The routine takes 194..322 cycles including RET, excluding the caller and IRQ.
This scalar C test does not execute or time the C decoder.

The first matched screen uses coverage, English `en_letter_a`, and Russian
`ru_slutskaya_a`, 128 frames each, with exact compact-oracle PCM and reset.

| WB3.95, all profiles linked | Before | Bounded divide |
| --- | ---: | ---: |
| Mean cycles/frame | 243283.622 | 241635.992 |
| Flash bytes | 24726 | 24734 |
| Static SRAM bytes | 1284 | 1284 |
| Peak stack bytes | 199 | 199 |

The screen saves 1647.63 cycles/frame (0.677%) for eight Flash bytes. It is
not an active-IRQ admission. Complete five-profile raw/IRQ, mixed-API and
long SPI checks are a separate validation stage. No physical board is measured.

```sh
python Codecs/Speex/AVR/tests/build_gain_div.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_gain_div.mjs Codecs/Speex/AVR/build/gain-div-unit
```

Original project optimization; the existing Xiph algorithm/table provenance
and licenses remain in their source files.

## Complete five-profile admission

Matched pre/post builds pass **106014 raw frames**: 53007 frames per version,
88 complete recordings/coverage streams per version, with independent compact
oracle PCM and reset replay. All optional low rates and NB4 are linked. The
32x32767 scalar check above covers the exact caller domain independently.

| Natural RU/EN speech | Before cycles/frame | After | Decoder CPU at 16 MHz |
| --- | ---: | ---: | ---: |
| WB3.95 | 241931.037 | 240283.600 | 75.60% -> 75.09% |
| WB5.75 | 244800.598 | 243151.286 | 76.50% -> 75.98% |
| WB7.75 | 245070.420 | 243421.107 | 76.58% -> 76.07% |
| WB9.8 | 236595.158 | 234945.845 | 73.94% -> 73.42% |
| WB12.8 | 238880.520 | 237231.645 | 74.65% -> 74.13% |

Speech means weight the verifier's rounded recording means by frame count.
Saving is about 1648 cycles/frame (0.67..0.70% decoder time); decoder CPU
falls about 0.515 percentage points. Across every full corpus, mean and
maximum frame cycles decrease. Every bare image grows eight Flash bytes;
static SRAM and measured peak stack stay identical to its matched baseline.

Fresh full-history output runs cover another **53007 frames** with production
PWM/timer IRQs, exact s16/PWM and zero underruns. Retain the established
per-mode additional CPU gates; the two forced-pitch modes are not claimed at 8%.

| Ready-RAM input | Frames | Extra cycles/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB3.95 | 10627 | 25600 (8%) | 3 | 411 B | 0 |
| WB5.75 | 10627 | 9600 (3%) | 13 | 386 B | 0 |
| WB7.75 | 10627 | 9600 (3%) | 19 | 381 B | 0 |
| WB9.8 | 10563 | 25600 (8%) | 6 | 396 B | 0 |
| WB12.8 | 10563 | 25600 (8%) | 5 | 389 B | 0 |

There are no resets inside a recording; timer intervals stay within
990..1010 cycles. Ready RAM excludes transport latency. Separate long SPI
runs cover **3600 WB3.95 / 2200 WB12.8 frames**, reading 36000 / 70400 bytes
from `0xff80` across 64 KiB boundaries. Actual AVR SPI/CS, the shared C model
and PWM interrupts remain active: every s16/PWM sample is exact, zero
underruns, minimum queues 29 / 30, free SRAM 408 / 386 B. Both SPI images
capture s16, unlike the older production WB3.95 observation. SPI has no extra
foreground load. No physical-board/analog claim is made.

Both variable public APIs pass 1024 mixed-mode frames, rejected calls,
readonly inputs, padding and reset. AVR C controls compile/link only:
NB11 stays byte-identical at 21098 B; WB3.95 grows 30710 -> 30968 B after
factoring its C expression into the inline helper. This is an ASM speed
optimization; no C decoder execution or timing is claimed. The exported
twenty-source C11 package compiles/links without assembly dependencies.

`reports/gain-div-admission.json` binds sources, firmware hashes, all corpus
input/oracle hashes and reports. It overlays two source changes on the
historical noise-cache admission and adds the private primitive/tests. Later
NB1 optimizations have their own source-bound admissions; these measurements
remain pinned to this bounded-divider stage.

```sh
python Codecs/Speex/AVR/tests/build_gain_admission.py --avr-gcc avr-gcc --baseline-root <noise-cache-codec-root> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_gain_admission.py --phase after --node node --low-corpus <low-corpus> --legacy-corpus <legacy-build> --spi-corpus <spi-corpus> --mixed-corpus <low-mixed> --spi-model <model.wasm>
# Other runner phases: before, irq, transport-api.
python Codecs/Speex/AVR/tests/audit_gain_div.py --low-corpus <low-corpus> --legacy-corpus <legacy-build>
```
