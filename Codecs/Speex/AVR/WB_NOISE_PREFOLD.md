# Hoist the invariant noise quantizer and remove zero products

Baseline: `56ffaa45` (exact quarter refills). Runtime: `836af17f`.
Target: ATmega328P / classic AVR5, 16 MHz, 2 KB SRAM, GNU ABI, AVR GCC 7.3.0,
existing Os/O2/O3 stages, LTO/mcall-prologues/mrelax, explicit ASM.
The affected production profile is compact WB3.95 / NB1 + HB1.

## Exact transform and lifetime

The previous five-symbol fold still repeated its first quantizer four times:

```c
t = (int16_t)(((int32_t)29491 * raw_noise[class]) >> 15);
r = (uint16_t)(((uint32_t)t * (uint32_t)subframe_gain + 256) >> 9);
out = odd ? (int16_t)(uint16_t)(0u-r) : (int16_t)r;
```

Only `subframe_gain` varies within a frame. Prepare the five `t` words once,
keeping the original raw words for `voc_previous`. Class2 is always exactly
zero, and its second-stage result is zero for every signed32 gain: `256 >> 9`.
Write that zero directly in both explicitly callable C and AVR implementations.
Keep the remaining floors, bias, narrowing, modulo32 behavior and late parity.
No gains are combined and no signal precision is reduced.

The first quantizer now needs four signed16 products/frame instead of twenty;
the second needs sixteen products instead of twenty. Hardware math MUL counts
fall from `4 * 5 * (4+7) = 220` to `4*4 + 4*4*7 = 128`: **92 fewer/frame**.
Four class-block address MULs remain unchanged. Observed preparation grows
88 -> 104 MULs/frame, while each of four fold controllers falls 56 -> 29.
The matched real API observer checks all 206 valid NB1 calls, including reset,
and verifies that rejected/other-mode calls execute no new preparation/fold.

The table reuses dead history words 99..103 / bytes 198..207. Existing classes
use bytes 0..159, raw words 160..169 and vocoder context 170..197. Delayed IIR input
begins at 210, leaving two guard bytes; the next history move reads from 320.
Workspace size is derived from the context/table constants and existing static
assertions verify both live-history boundaries. No persistent allocation changes.
The observer checks original excitation, all four partial states/seeds, raw and
Q15 words, class prefixes, the complete readonly 208-byte workspace during folds,
both guard bytes, output/scratch bounds and reset clearing.

`WB_FOLD_ARRAY` gains compile-time Q15/zero-class options while sharing the old
arithmetic macros, register saves and loop. The forty-word path retains its
original defaults. Old five-word full-fold entries remain isolated regression
references and are absent from the production image. The new five-word scale
entry skips loads/products for class2, preserves callee-saved registers/r1 and
never masks interrupts. The C implementation remains explicitly selectable on
AVR and other targets; existing architecture plus separate ASM-enable selection
and independent hardware-memory access are unchanged.

## Measured alternatives and exactness

All three 384-frame matched screens retain exact PCM/reset:

| Screen | Mean cycles/frame | Flash | Peak stack |
| --- | ---: | ---: | ---: |
| Parent quarter producer | 224296.693 | 25162 B | 200 B |
| Hoist all five first-stage products | 224078.693 | 25212 B | 200 B |
| Compress to four words, then reinsert zero | 224181.693 | 25296 B | 202 B |
| Keep five slots, skip the fixed zero | 223953.693 | 25158 B | 200 B |

The compressed table is rejected: copying/reordering and compiler spills cost
more than the removed arithmetic saves. Fewer abstract operations alone did
not establish a faster complete image. Retained screen reports identify each
firmware separately. The selected variant saves 343 cycles/frame and 4 B Flash.

The isolated seven-path test passes **88960 cases** against independent BigInt:
original forty-word ASM folding, new lookup with AVR/C scale, original full
five-word AVR/C leaves and new zero-aware AVR/C leaves. It sweeps all signed16
raw values in the four variable class slots, fixes the mandatory class2=0,
and covers all 32 caller scales, 183 structured signed32 gains and four subframes.
Readonly workspace, output/scratch guards and 355840 callee-saved/r1 returns pass.
Non-argument saved registers are randomized; valid overlapping argument registers
are preserved. Both direct leaves randomize all saved registers. The selected
controller takes 1353..1355 cycles including RET; its scale leaf takes 298..300.
No full C decoder is executed or timed.

## Complete decoder and output admission

Fresh WB3.95 tests pass **10627 frames / 18 streams** with reset checks: 6467 natural
RU/EN frames, 4096 coverage and 64 padding frames. Every PCM word matches the
unchanged independent compact-WB reference. Every recording's rounded mean
and maximum are exactly 343 cycles lower than the parent.

| Bare WB3.95 | Parent | Invariant Q15 + zero skip |
| --- | ---: | ---: |
| Natural speech cycles/frame | 222942.788 | 222599.788 |
| Decoder CPU at 16 MHz | 69.6696% | 69.5624% |
| Complete-corpus mean cycles | 224004.907 | 223661.907 |
| Complete-corpus max cycles | 226198 | 225855 |
| Flash | 25162 B | 25158 B |
| Static SRAM | 1284 B | 1284 B |
| Peak stack | 200 B | 200 B |
| Free SRAM at peak | 564 B | 564 B |

Speech means weight rounded recording means by frame count. The relative
speech-time improvement is 0.154%; 343 cycles are 21.44 microseconds at 16 MHz.
This is a small additional exact gain; the earlier quarter-refill improvement
remains a distinct stage.

| Continuous output | Frames | Extra cycles/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production IRQ, ready RAM | 10627 | 25600 (8%) | 30 | 410 B | 0 |
| Production IRQ, ready RAM | 10627 | 35200 (11%) | 22 | 410 B | 0 |
| Scheduled SPI transport | 3600 | 0 | 30 | 407 B | 0 |

All s16/PWM samples match with full recording history and timers active. Output
intervals remain within 990..1010 cycles. IRQ Flash is 25620 B; SPI capture is
25686 B Flash / 1422 B static SRAM / 219 B stack. SPI reads 36000 bytes at 0xff80,
crossing 64 KiB through the actual AVR SPI/CS schedule and unchanged W25Q128 model.
The preparation work moves earlier: maximum frame-boundary publication gaps
grow 113 cycles (7.06 microseconds), 94865 -> 94978 at +8% load and
105125 -> 105238 at +11%. Intra-frame maxima remain 80013 cycles; the full
loaded gates retain the same minimum queues. This small burst cost is accepted
alongside the measured overall speed/size gain. No stronger load or physical-
board/analog-output claim is made.

Both mixed APIs pass 1024 frames, 6144 NB / 7168 WB rejected calls, padding and
reset. The new WB fold records 824 calls / 23896 MULs versus 46144 previously.
Preparation adds 3296 MULs across 206 valid NB1 calls; net removal is 18952,
exactly 92 per valid frame. In a WB-enabled build the NB API also prepares the
unused Q15 words; a pure NB build does not. Fully enabled pure NB2.15 and four
minimum NB8/NB11/WB9.8/WB12.8 images rebuild byte-identically, retaining their
prior evidence. AVR C controls compile/link only: NB11 is 21004 B; WB3.95 grows
28 B to 31256 B. The 21-source portable C11 export links with no assembly.

The compact Q7/16-tap QMF, packet formats, noise sequence and vocoder arithmetic
remain unchanged. This stage preserves the existing compact-WB output exactly;
it does not replace the compact synthesis filter with full 64-tap Xiph QMF.

## Evidence and reproduction

`reports/noise-prefold-admission.json` binds sources, baseline admission, firmware
and reports, including rejected and intermediate screens. Historical reports
remain unmodified. Firmware/audio/log/DLL/WASM artifacts are not committed.

```sh
python Codecs/Speex/AVR/tests/build_noise_fold.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_noise_fold.mjs Codecs/Speex/AVR/build/noise-fold-unit
python Codecs/Speex/AVR/tests/build_noise_prefold_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --spi-stream <wb395/long.spxraw>
python Codecs/Speex/AVR/tests/run_noise_prefold_admission.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat for phases irq8, irq11 and transport-api.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_noise_prefold.py --corpus <low-corpus>
```

The matched old preparation-count run uses the parent's unchanged API binary
with `verify_low_api.mjs --count-noise-prepare --count-vocoder --count-noise-values`.
Screens are retained experiments; reproducing the full accepted admission does
not require rebuilding rejected variants. Source/template/register work is
original project work; retain Xiph's existing BSD provenance/notices.
