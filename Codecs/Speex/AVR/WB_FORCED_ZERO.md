# Skip exactly zero forced prediction

Baseline `056d3a73`; runtime `4f9edd67`. Target: ATmega328P, classic AVR5,
16 MHz, 2 KB SRAM, GNU ABI, AVR GCC 7.3.0 with the existing mixed Os/O2/O3,
LTO, mcall-prologues and mrelax recipe. Complete matched images enable all
lower rates (`--low-rates 7`) and NB4. NB8 below means **submode 8**, used by
NB3.95/WB5.75; it does not mean the default 8 kbit/s NB3 profile.

## Exact simplification

The four-bit coefficient code maps to
`min(63, (2185 * (code << 6) + 16384) >> 15)`. Across its sixteen values, only
code zero produces coefficient zero. In that case all adaptive prediction,
including recovered short-lag ancestry and pitch clipping, is exactly zero
for every possible history. Skip that calculation before computing the pitch
and coefficient. Decode the complete innovation and its original gain.
This is an algebraic case split, with no amplitude threshold or VAD decision;
quiet speech is not discarded.

The shared zero-innovation primitive accepts a twenty-word row directly:
four subframes, two rows each. Its existing byte-product ASM instructions are
unchanged. The variable-count interface is now proven for counts 0..20, rather
than 0..10; shape rounding bias remains **4**, independent of vector length.
The explicit C vector fallback remains selectable even on AVR. Assembly still
requires both the supported architecture and the separate enable define;
Flash access and public portable codec interfaces are unchanged.

No persistent buffer or state is added. Subsequent synthesis, delay history,
QMF, packet interpretation and reset behavior remain unchanged. A small
out-of-line frame procedure reuses the existing vector arithmetic. A measured
earlier variant branched after coefficient calculation: testing the raw code
instead saves another 12 B and about 79/82 cycles on the WB/NB screen.

## Complete-image measurements

Both before and after decode each full 18-stream / 10627-frame corpus:
42508 matched raw decoder frames, including resets. Each profile contains
6467 natural Russian/English frames, 4096 coverage and 64 padding frames.
All PCM matches the unchanged oracle. Zero coefficient occurs in 1923/6467
NB and 1903/6467 WB speech frames, about thirty percent of this corpus.

| Bare decoder | NB3.95 before | NB3.95 after | WB5.75 before | WB5.75 after |
| --- | ---: | ---: | ---: | ---: |
| Speech cycles/frame | 102391.888 | 96529.805 | 239941.368 | 234202.881 |
| Decoder CPU at 16 MHz | 31.997% | 30.166% | 74.982% | 73.188% |
| Full-corpus mean cycles | 102540.890 | 98429.781 | 240743.715 | 236707.553 |
| Full-corpus maximum cycles | 112378 | 112374 | 251723 | 251719 |
| Flash | 17128 B | 17266 B | 25394 B | 25538 B |
| Static SRAM | 1108 B | 1108 B | 1289 B | 1289 B |
| Peak stack | 115 B | 121 B | 199 B | 199 B |
| Free SRAM at peak | 825 B | 819 B | 560 B | 560 B |

These speech means use exact per-frame cycle sums. The parent note weights
rounded recording means, which differs by less than one cycle here. The
timed command includes the mailbox and excludes startup, reset and interrupts.
Nonzero-coefficient frames are **four cycles faster in every matched case**.
Zero-coefficient frames save 16720..27448 cycles for NB and 16728..27464 for WB.
Mean speech decoding time improves about 5.73% NB / 2.39% WB. The tradeoff is
138/144 B Flash and six additional NB peak stack bytes; WB stack is unchanged.

| Continuous output | Frames | Added work/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB5.75 ready-RAM IRQ | 10627 | 9600 cycles (3%) | 14 | 406 B | 0 |
| NB3.95 scheduled SPI | 4096 | 0 | 74 | 654 B | 0 |
| WB5.75 scheduled SPI | 2200 | 0 | 23 | 403 B | 0 |

All runs retain continuous recording history and exact s16/PWM with active
timers and interrupts. WB IRQ uses 25988 B Flash / 1430 B static SRAM / 212 B
stack; scheduled SPI uses 17558/26064 B Flash, 1251/1427 B static SRAM and
143/218 B stack for NB/WB. Output intervals stay within 1994..2004 cycles NB
and 990..1010 cycles WB. SPI reads 40960/33000 compressed bytes from 0xff80,
crossing 64 KiB with actual SPI/CS through the unchanged shared W25Q128 model.
The SPI cases total 1359360 exact samples. No standalone NB ready-RAM IRQ
admission is claimed. These are ISA-simulator results, not physical-board or
analog measurements.

## Arithmetic, memory and API evidence

The isolated vector fixture passes **37024 cases**: all 32 rows, 49 unique
scales including all 32 caller scales, every count 0..20 and 4096 random cases.
ASM and the explicit C primitive match both the original Q14 decomposition
and an independent wide-integer formula. Fixed ten-word controls remain 501
cycles; variable twenty-word calls take 965 cycles, versus two fixed calls at
1002 cycles before caller overhead. Count zero takes six cycles and accepts
null pointers without any memory access.

Guards, untouched tails, exact Flash addresses, no output reads, randomized
saved registers and all 42354 GNU ABI/r1 returns pass. The complete isolated
firmware is byte-identical when assembled with the parent's arithmetic source:
the optimization changes control flow and the proven count domain, not ASM
arithmetic instructions.

Mixed APIs each pass 1024 frames plus 6144 NB / 7168 WB rejected calls,
padding and reset checks. Observers see 42 NB / 44 WB fast frames, exactly
eight contiguous twenty-word calls each, 652 MULs per fast frame and no
adaptive-kernel calls or excitation-history/output reads in that producer.
The remaining shape reconstruction is preserved.

Single-feature NB8-only ASM images pass 384-frame screens: NB3.95 12588 B,
WB5.75 19414 B. Their C images (13996/22648 B), full-feature C SPI controls
(21296/31552 B) and the 21-source portable C11 export compile/link only.
Only isolated C arithmetic executes; the full C decoder is not run or timed.
Four minimum images without NB8 (NB8 kbit/s, NB11, WB9.8, WB12.8) remain
byte-identical. No fresh complete all-feature timing claim is made for other
profiles. Compact Q7/16-tap QMF remains unchanged; this is not full 64-tap
Xiph WB synthesis.

## Reproduction

`reports/forced-zero-admission.json` binds runtime/test source hashes, baseline
provenance, retained reports and firmware hashes. Parent reports remain intact.
The before-source tree is checked against the parent's 157-file admission.
Per-frame traces stay in ignored build output; their paired aggregate,
including exact speech sums and coefficient classes, is retained. Generated
firmware, PCM, logs and model binaries are not committed.

```sh
python Codecs/Speex/AVR/tests/build_forced_zero_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --low-corpus <low-corpus> --spi-corpus <spi-corpus>
node Codecs/Speex/AVR/tests/verify_zero20.mjs Codecs/Speex/AVR/build/zero20-unit
python Codecs/Speex/AVR/tests/run_forced_zero_admission.py --phase before --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat phases after, irq and transport-api.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_forced_zero.py --corpus <low-corpus>
```

The post-quantization variant is a retained experiment; accepted admission uses
the early raw-code branch. Control/test adaptations are original project work;
existing Xiph algorithm/table provenance and BSD notices remain intact.

Further candidates are a dedicated one-tap nonzero predictor, an exact smaller
Q6 ancestry product, and section ownership for the shared ASM vector body.
They remain unmeasured and are not included in the results above.
