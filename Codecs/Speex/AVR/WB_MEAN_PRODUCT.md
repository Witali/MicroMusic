# One exact product for the NB1 vocoder mean

Baseline: `4107d9f3`, with exact bounded HB1 division. Target: classic AVR5 /
ATmega328P, 16 MHz, GNU ABI, AVR GCC 7.3.0, explicit ASM. NB2.15 and its
compact WB3.95 combination use this mean; the other submodes do not.

The original update is `floor((26214*old + 6554*value + 16384)/32768)`.
Because the coefficients sum to 32768, it equals
`old + floor((6554*(value-old) + 16384)/32768)`. Both inputs are signed16,
but their difference needs seventeen signed bits. If signed16 subtraction
wraps, the missing +/-65536 contributes an exact integer correction of
`+/-13108`, since `6554*65536/32768 = 13108`. AVR's V flag detects this case;
the wrapped result's sign chooses the correction. LDI preserves these flags.

The single signed16 product needs four hardware MUL instructions instead of
eight in the old two-product inline expansion. Rounded extraction keeps bits
15..30; additions of the base/correction are modulo 16 bits, as is the
original returned word. The original convex weighted sum plus rounding fits
signed32, so the algebra introduces no signed overflow or approximation.

`src/lowrate_mean.S` is an 82-byte shared subroutine. It uses only GNU
call-clobbered r18..27 and flags, clears r1, and adds no local stack, hardware
memory access or interrupt masking. The original two-product C expression
remains explicitly callable in `lowrate_mean.h`, including in ASM builds.
Default/unsupported architectures use C through the existing architecture
selector plus separate ASM enable. Memory access is independent of selection.

The isolated real-ABI test checks 1,212,335 pairs: nine complete signed16
sweeps per operand (without duplicate edge intersections) and 32768 random
pairs. Both overflow directions, C fallback and ASM match independent BigInt
arithmetic. Arbitrary callee-saved patterns and r1 pass every return. Every
call executes exactly four MULs and takes 43..48 cycles including RET,
excluding CALL and IRQ. This test does not execute or time the C decoder.

## Matched initial screen

AVR GCC 7.3.0, existing Os/O2/O3/LTO/mcall-prologues/mrelax, avr8js 0.21.1.
Same three 128-frame streams: coverage, English `en_letter_a`, Russian
`ru_slutskaya_a`; exact established-oracle s16 PCM. All optional modes linked.

| Screen | Before | One product |
| --- | ---: | ---: |
| WB3.95 mean cycles/frame | 241635.992 | 238690.076 |
| WB3.95 Flash / static SRAM / peak stack | 24734 / 1284 / 199 B | 24690 / 1284 / 199 B |
| NB2.15 Flash / static SRAM / peak stack | 17302 / 1104 / 118 B | 17216 / 1104 / 112 B |

WB saves 2945.92 cycles/frame (1.219%) and 44 B Flash. NB saves about 3771
cycles/frame and 86 B Flash, with six fewer peak stack bytes. A subroutine
therefore improves both measured speed and size here. Exactly 160 mean calls
per NB1 frame remove **640 hardware multiplies/frame**; this is not the
multiply count for the complete decoder. Complete corpus/IRQ/SPI admission is
a separate stage. No physical board or analog output measurement is claimed.

```sh
python Codecs/Speex/AVR/tests/build_low_mean.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_low_mean.mjs Codecs/Speex/AVR/build/mean-unit
```

Original project algebra/register implementation, retaining Xiph algorithm
provenance and licenses in the surrounding source/vendor files.

## Complete affected-mode admission

Fresh ASM runs pass **10627 frames / 18 streams each** for NB2.15 and WB3.95,
with exact independent-oracle PCM and first-frame replay after every reset.
Each corpus includes 6467 natural RU/EN frames, 4096 coverage frames and 64
padding frames. Matched before data is retained only after its binary hash
matches the freshly built screen image; the NB baseline is unchanged by HB1
division. Speech averages below weight the sixteen recordings by frame count
and use the verifier's rounded per-recording cycle means.

| Natural speech | Before mean change | One product | Decoder CPU, 16 MHz |
| --- | ---: | ---: | ---: |
| NB2.15 | 106972.616 cycles/frame | 103201.616 | 33.43% -> 32.25% |
| WB3.95 | 240283.600 cycles/frame | 237337.974 | 75.09% -> 74.17% |

The mean change saves **3.53% NB / 1.23% WB** on this corpus. Together with
bounded gain division it reduces WB3.95 speech decoding 75.60% -> 74.17% CPU
relative to the preceding noise-cache stage. No feedback precision, RNG,
rounding, packet format or compact QMF setting changes.

| Continuous WB3.95 output | Frames | Added load/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production IRQ, ready RAM input | 10627 | 25600 cycles (8%) | 6 | 411 B | 0 |
| Actual scheduled SPI, captured s16/PWM | 3600 | 0 | 32 | 408 B | 0 |

The first gate runs full recording histories without chunk resets. Timer
intervals stay within 990..1010 cycles. The SPI gate reads 36000 compressed
bytes from `0xff80`, crossing 64 KiB, through the shared W25Q128 model and
real AVR SPI/CS path with active interrupts. Every s16 and PWM sample matches;
there is no additional foreground load in the SPI run. The IRQ image uses
25152 B Flash; the SPI observation image uses 25218 B, 1422 B static SRAM
and 218 B peak stack. Simulator evidence does not establish board timing.

Both mixed-mode public APIs pass 1024 frames, 6144/7168 rejected calls,
padding, readonly inputs and reset. The verifier observes the actual mean
routine in the decoder: 32960 calls and 131840 MULs per API run, exactly 160
calls / 640 MULs per valid NB1 frame, including reset replay. Every observed
result also matches the independent old two-product formula. Rejected calls
and other submodes execute no mean update.

With lower-rate features disabled, freshly rebuilt NB8/NB11/WB9.8/WB12.8
images are byte-identical to the bounded-division baseline. Their old evidence
is retained explicitly; this is not a fresh full run of all five WB modes.
AVR C images compile/link and remain byte-identical to that same baseline:
21098 B NB11 and 30968 B WB3.95. The exported twenty-source C11 package also
compiles/links without `.S`. The C decoder is not executed or timed.

`reports/mean-product-admission.json` binds sources and evidence, overlaying
five modified files on the historical noise-cache source manifest and adding
the gain/mean primitives and tests. Historical audits remain pinned.

```sh
python Codecs/Speex/AVR/tests/build_mean_admission.py --avr-gcc avr-gcc --baseline-root <bounded-divider-codec-root> --spi-stream <wb395/long.spxraw>
python Codecs/Speex/AVR/tests/run_mean_admission.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat the runner with --phase irq and --phase transport-api.
python Codecs/Speex/AVR/tests/audit_mean_product.py --corpus <low-corpus>
```
