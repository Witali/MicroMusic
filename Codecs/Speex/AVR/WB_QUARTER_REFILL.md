# Exact quarter-frame NB1 excitation

Baseline: `ab597728`, with finite-alphabet folding. Runtime change: `062f5306`.
Target: ATmega328P / AVR5, 16 MHz, 2 KB SRAM, GNU AVR ABI, AVR GCC 7.3.0,
existing Os/O2/O3 stages, LTO, mcall-prologues and mrelax, explicit ASM.
This stage changes WB3.95's NB1 producer and the shared scalar NB1 mean.

## Scheduling and arithmetic

The old producer constructed all 160 excitation samples before the first
synthesis callback. Average throughput passed, but the +11% foreground-load
test drained the PWM queue. Keep the original forty-sample IIR delay and
generate forty excitation samples before each synthesis quarter. All random
transitions, raw noise words, pulse/mean feedback, quantizers and final state
remain exact. The public interfaces and 128-sample output ring are unchanged.

Prepare the two five-word gain tables, two pulse words, prior noise and pitch
once per frame. These fourteen words reuse dead excitation-history bytes
170..197 after the frame move. Classes occupy 0..159 and raw words 160..169.
The first live delayed input starts at 210; the next history move reads from
320. Static assertions bind the geometry. Each quarter constructs only its
forty classes and excitation words; later quarters do not inspect stale classes.
Other NB modes retain their existing producer. Pure NB builds without WB retain
the old whole-frame controller and benefit only from the scalar mean change.

`nb1_vocoder.S` keeps constants and feedback in registers for forty samples.
An equivalent phase countdown replaces the original sample-index comparison.
The same exact mean macro serves the scalar and vector entries, parameterizing
the mean/product registers and preserving r20 for the vector count. Discarding
unobservable product bits 0..7 removes one scalar move, reducing its function
from 43..48 to 42..47 cycles; the four-MUL mean and overflow correction remain.
The vector saves all used GNU callee registers, clears r1 and never masks IRQ.

`nb1_vocoder.c` remains explicitly callable and selectable on AVR. It uses the
original absolute phase and two-product C mean. The existing architecture plus
separate explicit ASM-enable selector controls arithmetic; default/unknown
targets use C. Hardware memory access remains independent.

## Rejected experiment and exactness

An initial C controller split passed the same 384-frame PCM/reset screen but
cost 230344.068 cycles/frame versus 227325.068 for the parent, so it was rejected.
The fused AVR version takes 224296.693 on that matched sample. The rejected
measurement is retained separately; it does not constitute a C decoder test.
Both controllers used the ASM arithmetic backend.

The new isolated vector test executes explicit C/ASM primitives against an
independent BigInt model of the original two-product mean. It passes 31540
cases: a full signed16 table-word sweep and all 18432 valid pitch/phase pairs,
including a phase beyond a newly selected pitch. Forty PCM words, all cursor
fields, readonly inputs, output bounds, arbitrary callee-saved patterns and r1
match. It observes exactly 160 hardware MULs per call, 3172..3284 cycles including
RET. The shared scalar passes 1212335 C/ASM/reference pairs and ABI returns.
No full C decoder is executed or timed.

A separate actual-decoder observer passes 1024 mixed frames, with 205 NB1 frames
and 820 generated/folded quarters. It independently reconstructs Xiph's pinned
sqrt polynomial, noise/gain formulas, pulse/mean state and RNG. It checks each
new excitation block before filtering, every partial vocoder state/seed, raw
word table, valid class prefix, twelve guard bytes, delayed history and next
move bounds. Fold calls preserve the entire 198-byte workspace and use exactly
five scratch words. Reset clears the reused workspace.

## Full output and timing evidence

Fresh bare NB2.15 and WB3.95 runs each pass 10627 frames / 18 streams with reset
replay: 6467 natural RU/EN speech frames, 4096 coverage and 64 padding. PCM words
match the established independent references. The compact Q7/16-tap WB QMF is
unchanged; this is bit-exact to the existing compact profile, not full 64-tap QMF.

| Bare WB3.95 | Parent | Quarter producer |
| --- | ---: | ---: |
| Natural speech cycles/frame | 225973.224 | 222942.788 |
| Decoder CPU at 16 MHz | 70.62% | 69.67% |
| Complete-corpus mean cycles | 227033.308 | 224004.907 |
| Complete-corpus max cycles | 229268 | 226198 |
| Flash | 24876 B | 25162 B |
| Static SRAM | 1284 B | 1284 B |
| Peak stack | 200 B | 200 B |
| Free SRAM at peak | 564 B | 564 B |

Speech means weight rounded recording means by their frame counts. Speech
decoding improves 1.34%; complete-corpus time improves 1.33%. Pure NB2.15 saves
exactly 160 cycles/frame and 2 B Flash: 17128 B Flash / 1104 B static SRAM /
110 B peak stack / 834 B free. Four minimum NB8/NB11/WB9.8/WB12.8 images rebuild
byte-identically, retaining their earlier evidence rather than claiming fresh
full-mode runs.

| Continuous WB3.95 output | Frames | Extra cycles/frame | Min queue | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production IRQ, ready RAM | 10627 | 25600 (8%) | 30 | 410 B | 0 |
| Production IRQ, ready RAM | 10627 | 35200 (11%) | 22 | 410 B | 0 |
| Scheduled SPI transport | 3600 | 0 | 30 | 407 B | 0 |

All s16 and PWM samples match with unbroken recording history and active timers.
IRQ output intervals remain within 990..1010 cycles. IRQ firmware occupies
25624 B Flash. SPI capture uses 25690 B Flash / 1422 B static SRAM / 219 B peak
stack and reads 36000 bytes starting at 0xff80 through real AVR SPI/CS and the
shared C W25Q128 model, crossing 64 KiB. Its minimum queue is 30 versus the
parent's 36: changing producer scheduling does not improve every transport
queue metric, although this complete run retains zero underruns and exact output.

Publication timing observes the actual ring head write after all eighty bytes
are ready. On a matched 384-frame, three-stream +8% IRQ sample, maximum gaps
across frame boundaries improve 117458 -> 94865 cycles (~19.2%). Intra-frame
gaps remain timer-paced at about 80013 cycles. Full-corpus reports also retain
publication counts and per-recording maxima. The old +11% failure remains in
the historical fold admission; the new full +11% run passes. Ready RAM excludes
transport delay; SPI has no injected foreground load. No physical board or
analog-output measurement is claimed.

Both APIs pass 1024 mixed frames, 6144 NB / 7168 WB rejected calls, padding and
reset. Each records 824 vocoder calls / 131840 MULs: four calls and 640 mean MULs
per valid NB1 frame, none for rejected calls or other modes. WB fold remains
824 calls / 46144 MULs. C controls compile/link only: NB11 21004 B, WB3.95
31228 B. The self-contained 21-source portable C11 package links without ASM.

## Reproduce and inspect

`reports/nb1-refill-admission.json` binds the exact sources, baseline admission,
reports and firmware hashes. Historical audits remain pinned. Generated
firmware, audio, DLLs, logs and the WASM model are not committed.

```sh
python Codecs/Speex/AVR/tests/build_nb1_refill_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --spi-stream <wb395/long.spxraw>
node Codecs/Speex/AVR/tests/verify_nb1_vocoder.mjs Codecs/Speex/AVR/build/vocoder-unit
node Codecs/Speex/AVR/tests/verify_low_mean.mjs Codecs/Speex/AVR/build/mean-unit
python Codecs/Speex/AVR/tests/run_nb1_refill_admission.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat for phases irq8, irq11 and transport-api.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_nb1_refill.py --corpus <low-corpus>
```

The retained rejected controller and matched publication-gap screen are local
experiments recorded in the reports; full admission reproduction does not need
to rebuild the rejected controller. The export checker targets the tested Windows
Clang toolchain and only links a DLL; it does not load it.

[Reusable technique and constraints](../../../docs/avr-asm-cookbook/speex-quarter-refills.md).

## Remaining unmeasured candidates

- Hoist the five first-stage Q15 noise transforms across all four subframes.
  The current context leaves twelve guard bytes; another ten-byte table would
  require a new lifetime/bounds proof. Preserve the raw noise state and quantizers.
- Reuse the geometry-parametric fused reconstruction/fold kernel for WB5.75
  and WB7.75, retaining the bias independently of vector count.
- Specialize the bounded Q6 forced-pitch product or the 128-value pitch-sqrt
  input domain only after measuring a complete image with exact PCM/IRQ output.
