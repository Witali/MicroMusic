# Exact noise-generator speed work

Target: ATmega328P / 16 MHz / 2 KB SRAM, explicit AVR ASM, AVR GCC 7.3.0
with the existing mixed Os/O2/O3, LTO/mcall-prologues/mrelax. The baseline is
`f661fff5`, including the optional lower profiles and shared SPI input.
No synthesis precision, sample rate, packet layout or random state is changed.

## Seven byte products instead of ten

The Xiph noise recurrence is `next = 1664525*seed + 1013904223 (mod 2^32)`.
The multiplier is `0x0019660d = 13 + 102*256 + 25*65536`.
A general AVR 32-bit multiply computes ten byte products in this workload.
Dropping the zero top coefficient leaves nine; reusing `25*x = 2*(13*x)-x`
for the two low seed bytes leaves **seven hardware MUL instructions**.

Initialize the result's upper word with `25*x0` instead of zeroing it, then
adding a separately multiplied value later. The contribution of `25*x1` needs
only its low byte at bit 24. Preserve every carry between bytes and discard
only bits beyond bit 31. Constants 13 and 102 are register inputs so the
forty-sample caller hoists their loads outside its loop.

`src/lowrate_rng.h` keeps the original unsigned C recurrence explicitly
callable, including in an ASM build. Architecture matching and the independent
`SPEEX_NB3_ENABLE_ASM` opt-in select ASM; otherwise the same C formula is used.
The optimization is arithmetic only, independent of Flash access. GNU inline
ASM declares r0/r1/r2 and condition-code clobbers; r1 is cleared before return.

## Measured candidate screen

Three 128-frame streams: `coverage4096`, `en_letter_a`, `ru_slutskaya_a` from
the retained WB3.95 corpus. Each run compares exact s16 PCM and reset output
with the independent compact-QMF oracle. Timings exclude IRQ/output.

| Candidate | Mean cycles/frame | Flash bytes | Static SRAM | Peak stack |
| --- | ---: | ---: | ---: | ---: |
| Original generic multiply | 269031.878 | 24750 | 1288 | 211 |
| Nine MUL, one factor register | 258945.846 | 24796 | 1288 | 210 |
| Nine MUL, hoisted factors | 258385.846 | 24804 | 1288 | 210 |
| Seven MUL, reused products | 257745.846 | 24804 | 1288 | 210 |

The chosen candidate saves 11286.031 cycles/frame, about **4.20%** on this
screen, for +54 B Flash, unchanged static SRAM and one less peak stack byte.
This affects NB2.15/WB3.95, whose noise generator is called; other rates do
not gain the same reduction. This is not a perceptual quality modification.

The isolated primitive unit checks 135243 seeds against an independent
unsigned-32 reference, covering every low word, every high word, bit boundaries
and deterministic random cases. It checks C and ASM arithmetic, ten versus
seven actual multiply instructions, and 135243 r1/callee-saved returns with
arbitrary injected register patterns. This is not a C decoder runtime test.

Original C NB11/WB3.95 SPI images rebuild byte-identically; new C decoder
simulations are excluded. Lower-rate-disabled ASM images remain byte-identical
to the four previous minimal builds. The portable C11 export compiles/links
with the new private header and no `.S` source dependencies.

## Full admission completed

Each affected rate passes its complete 10627-frame corpus with exact PCM and
18 first-frame reset checks: **21254 decoder frames**. That includes 16
Russian/English recordings, constructed coverage and ignored-padding streams.
The same mixed-mode API tests pass 1024 frames per family and all rejected
calls, including switching among modes 1/2/8/3/4 without resetting state.

| Speech profile | Baseline cycles/frame | New cycles/frame | Decoder CPU before/after |
| --- | ---: | ---: | ---: |
| NB2.15 | 112616 | 106973 | 35.19% / 33.43% |
| WB3.95 | 267682 | 256396 | 83.65% / 80.12% |

Speech figures are frame-weighted from the rounded per-stream means, on the
same 6467 natural frames. WB speech improves **4.22%**, NB **5.01%**. Across
all WB frames, mean cycles decrease 268741.4606 -> 257454.9203 and maximum
270961 -> 259661. Bare Flash grows 17248 -> 17302 B NB and 24750 -> 24804 B
WB; static SRAM stays 1104/1288 B and peak stack decreases 119/211 -> 118/210.

The production WB IRQ/queue code passes all 10627 frames both normally and
with **19200 extra foreground cycles/frame (6%)**: **21254 IRQ frames**, exact
s16/PWM, zero underruns. Minimum queues are 26 normally and 5 at +6%; free
SRAM is 396 B in both. The preceding implementation admitted +3% on this
profile. Ready-RAM delivery does not include transport delay.

A separate continuous **3600-frame / 36000-byte SPI stream** passes with exact
entire PWM, zero underruns and minimum queue **25**, versus 17 before. The
production SPI image grows 25260 -> 25316 B Flash; static SRAM remains 1422 B,
peak stack decreases 230 -> 229 B and free SRAM rises 396 -> 397 B. Actual
SPI controller completion, GPIO CS, timers and IRQ remain modeled. No extra
foreground work is added to that SPI test; no physical board is measured.

An exploratory +8% ready-RAM screen fails on its first 128-frame coverage
stream (380 underruns); that load is **not admitted**. Counts, report hashes
and current source hashes are retained in `reports/noise-speed-*.json`.
The audit overlays the one changed noise C file on the historical lower-rate
source contract; older audits remain pinned to the previous implementation.
Five final decoder/IRQ/SPI images rebuild byte-identically.

```sh
python Codecs/Speex/AVR/tests/build_low_rng.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_low_rng.mjs Codecs/Speex/AVR/build/low-rng-unit
python Codecs/Speex/AVR/tests/build_noise_admission.py --avr-gcc avr-gcc --spi-stream <long-WB3.95-file>
python Codecs/Speex/AVR/tests/audit_noise_speed.py --corpus <lower-corpus> --avr-gcc avr-gcc --spi-stream <long-WB3.95-file>
```

The builder prepares mailboxes for the existing `verify_avr.mjs`, `verify_wb.mjs`,
`verify_wb_stream.mjs`, `verify_low_api.mjs` and `verify_spi_player.mjs` tools.
Its SPI input is `spi-corpus/wb395/long.spxraw` from `prepare_spi_streams.py`;
the adjacent `spi-corpus/nb11/long.spxraw` fixture is also needed for the
compile-only NB C identity check.
The audit validates the retained complete reports and optionally rebuilds five
images; it does not repeat the excluded C decoder runtime suite.

## Next opportunity: eliminate repeated noise generation

Inspection identifies a possible larger reduction, not implemented here.
WB3.95 currently regenerates 160 noise symbols after the low band already
generated them. With a frame excitation offset of 145 words and a 40-sample
IIR delay, low-band synthesis first reads old history at word 105, byte 210.
The first 210 history bytes are dead during NB1 synthesis, and the next frame
copies its history from word 160 onward. A 160-byte class sequence plus ten
bytes of already scaled noise values would fit before byte 210, without a new
RAM allocation. This needs explicit lifetime/bounds assertions, mixed-mode
history tests and fresh active-IRQ/SPI admission before using that space.
