# Fold the finite noise alphabet before expansion

Baseline: `86ae0365`, including exact gain division, one-product mean and
power-of-two noise scaling. Target: ATmega328P / AVR5, 16 MHz / 2 KB SRAM,
GNU ABI, AVR GCC 7.3.0, explicit ASM. This changes only NB1 + HB1 / WB 3.95.

## Exact algorithm

Each subframe has forty noise classes but only five possible `int16_t` words.
Its HB1 gain is constant. Apply the original transform once to each word,
then look up the transformed word and apply output-position parity. This
reduces **160 -> 20 transformations/frame** without approximating them.

Keep both original quantizers:

```c
t = (int16_t)(((int32_t)29491 * value) >> 15);
r = (uint16_t)(((uint32_t)t * (uint32_t)gain + 256) >> 9);
out = odd ? (int16_t)(uint16_t)(0u-r) : (int16_t)r;
```

In particular, do not combine the gains, negate an unrounded input, or apply
parity according to the table index. Each subframe starts at an even sample
offset (40 x sub), so local output parity matches frame parity.

`wb_fold.c` shares table copying and expansion between explicitly callable
C and AVR paths. The C path remains available even in ASM builds. Default or
unsupported architectures select C through the existing architecture plus
separate ASM-enable mechanism; hardware memory access stays independent.

`wb_fold.S` factors the existing forty-word loop into `WB_FOLD_ARRAY`, using
the unchanged Q15/SCALE macros for both forty alternating samples and five
non-alternating table words. The latter uses the preserved zero r2 as its
parity source. No new arithmetic approximation is introduced. The old forty-
word variant remains byte-identical in rebuilt minimum-mode controls.

The caller reuses five words of `interp[8]` after LSP conversion. `ak[8]`
remains live until its later denominator copy and is a distinct object.
A static assertion binds scratch capacity; the output of forty words, cache
of 170 readonly bytes and scratch of five words must be disjoint. The unused
private raw cache-expansion function is removed. No public interface or
additional persistent buffer is introduced.

## Arithmetic and memory evidence

The five-path harness compares the old forty-sample ASM procedure, new lookup
procedure, explicit C lookup, direct five-word ASM leaf and direct C leaf
against independent BigInt arithmetic on **88960 cases**. It sweeps all
65536 signed 16 words at every table slot, all 32 caller scales, 183 structured
gains including signed 32 extremes, and all four subframes. Output/scratch
guards and the readonly 170-byte cache pass. All monitored returns preserve
callee-saved registers/r1 (266880 checks).

AVR arguments can overlap call-saved registers: this five-argument interface
uses r14:15 for scratch and r16..19 for gain. The test preserves valid incoming
argument values, randomizes other saved registers, and verifies every saved
register on return. The direct two-argument ASM leaf separately randomizes
all saved registers. No C decoder is executed or timed.

Actual controller MUL counts fall **441 -> 56 per subframe**: folding itself
440 -> 55, plus one unchanged multiplication for the class-block address.
That removes **1540 hardware MULs/frame**. The unit controller takes
4230..4240 -> 1506..1507 cycles including RET; the new leaf takes 451..452.

A separate 1024-frame mixed-mode cache observer verifies 820 real lookup
calls, original RNG/scale equations, unchanged seed progression, readonly
cache, forty guard bytes before delayed input byte 210, the old delayed
history and scratch/output boundaries. Caller addresses come from actual
compiled arguments and geometry metadata. Five scratch words match the old
formula; adjacent caller words stay unchanged.

## Full decoder and output admission

The fresh WB 3.95 image passes **10627 frames / 18 streams** and reset replay:
6467 natural RU/EN frames, 4096 coverage and 64 padding frames. Every s 16 word
matches the established independent compact-WB oracle. AVR GCC 7.3.0, existing
Os/O2/O3, LTO/mcall-prologues/mrelax, avr8js 0.21.1:

| Natural speech / bare decoder | Before | Finite-alphabet fold |
| --- | ---: | ---: |
| Cycles/frame | 236697.974 | 225973.224 |
| Decoder CPU, 16 MHz | 73.97% | 70.62% |
| Flash | 24604 B | 24876 B |
| Static SRAM | 1284 B | 1284 B |
| Peak stack | 199 B | 200 B |
| Free SRAM at peak | 565 B | 564 B |

Speech means weight rounded recording means by frame count. Natural-speech
time improves **4.53%**; full-corpus mean is 227033.308 cycles, maximum 229268.
The cost is 272 B Flash and one extra peak stack byte, with unchanged static
SRAM and identical PCM. The original feedback precision, RNG, packet formats
and compact Q7/16-tap QMF are unchanged.

| Continuous output | Frames | Extra cycles/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production IRQ, ready RAM | 10627 | 25600 (8%) | 9 | 410 B | 0 |
| Actual scheduled SPI | 3600 | 0 | 36 | 407 B | 0 |

Every s 16/PWM sample matches with full recording history and active timers.
IRQ intervals stay within 990..1010 cycles. Ready RAM excludes transport;
SPI reads 36000 bytes from `0 xff 80` through actual SPI/CS and the shared C
model, crossing 64 KiB, at zero extra load. IRQ Flash is 25338 B; SPI capture
uses 25404 B Flash / 1422 B static SRAM / 219 B peak stack. No board/analog
measurement is claimed.

The **11% stress experiment is rejected**: coverage 4096 decodes to exact s 16
but output records 8083 underruns, so its full-corpus/PWM checks do not pass.
Only the completed 8% gate is admitted. Average CPU saving alone does not
prove the next-block deadline; future work should shorten the initial burst.

Both public APIs pass 1024 mixed frames, errors, padding and reset. Actual
WB observation confirms 824 calls / 46144 MULs, twenty transformed values and
220 fold MULs per valid NB1 frame (224 including class-block addressing).
Other modes and rejected calls execute no new fold. NB 2.15 and four minimum
NB 8/NB11/WB 9.8/WB 12.8 images rebuild byte-identically; retain their prior
evidence explicitly. C controls compile/link only (NB11 21004 B, WB 3.95
31032 B). The twenty-source C 11 export links without assembly dependencies.

`reports/noise-fold-admission.json` binds sources, firmware and evidence,
including the rejected stress experiment. Older audits remain pinned.

```sh
python Codecs/Speex/AVR/tests/build_noise_fold.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_noise_fold.mjs Codecs/Speex/AVR/build/noise-fold-unit
python Codecs/Speex/AVR/tests/build_noise_fold_admission.py --avr-gcc avr-gcc --baseline-root <noise-shift-codec-root> --spi-stream <wb395/long.spxraw>
python Codecs/Speex/AVR/tests/run_noise_fold_admission.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Other phases: irq8, transport-api; irq11 is the rejected stress experiment.
python Codecs/Speex/AVR/tests/audit_noise_fold.py --corpus <low-corpus>
```

Original project algorithm/register work; existing Xiph provenance and BSD
notices remain in the source/vendor files.

## Unmeasured next candidates

- Generate NB1 excitation forty samples at a time instead of constructing
  all 160 before the first callback. The current forty-byte dead gap after
  the 170 cache bytes could hold 28 bytes of frame-constant vocoder context,
  ending at 198 before live input 210. Preserve the complete generated class
  sequence, raw noise words, mean/pulse/seed order, final state and delayed
  input; validate each class prefix when visible. Measure both average cost
  and worst refill delay before claiming the 11% gate. No larger ring is
  assumed. This has not been implemented or validated.
- Hoist the five first-stage Q15 transforms across four subframes: that
  stage depends on frame noise scale, while only the second stage uses each
  subframe gain. Prove any extra dead-prefix workspace/lifetime and retain
  original raw noise for vocoder state. No saving is claimed yet.
- Fuse WB 5.75/7.75 codebook reconstruction and folding using the existing
  geometry-parametric kernel, with its exact original quantizers.
