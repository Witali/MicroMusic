# Wideband improvement plan

Target: ATmega328P, 16 MHz, 2 KB SRAM; compact WB3.95/5.75/7.75/9.8/12.8,
mono 16 kHz.
The explicitly enabled AVR ASM backend is the performance target. Retain
the portable, explicitly selectable C fallback and existing backend selection.

## Current speed cycle, 2026-11-03

[Bounded LPC-response division](WB_RATIO_SPEED.md) replaces the remaining
generic gain-ratio divide for all five WB rates. Scalar domain/ABI/IRQ proofs,
matched five-rate screens, complete raw comparisons and complete loaded output
checks pass on the available corpus. The original sound is preserved.
The [combined response/QMF/IIR stage](WB_FINITE_RESPONSE.md) now passes all
34869 available frames in both raw epochs and another 34869 loaded output frames,
including HB interpolation and signed16 response arithmetic. Exact split QMF
accumulators and finite pitch-root lookup offer the next implementation steps.
Speed remains the first priority; do not mark
the broader optimization goal complete while these useful candidates remain.

## Acceptance rules

- Separate exact speed changes from intentional synthesis/quality changes.
- Exact changes must preserve every signed16 output, reset, history, permitted
  QMF alias, saturation and rounding. Keep existing independent oracles.
- Measure cycles, Flash, static SRAM and peak stack with the same pinned
  compiler/options and input bytes before/after. Reject unexplained regressions.
- Recheck continuous output with production timers/interrupts and queue code,
  including the established 8% additional work for WB9.8/WB12.8. Lower rates
  must preserve their separately measured admission and test a larger reserve;
  WB3.95 previously admitted 3%. Ready RAM packets do not establish
  storage/serial latency or physical-board timing.
- Do not rerun the excluded Speex C performance suite. When C sources and
  dependencies remain unchanged, bind their previous reference evidence by
  hashes; do not describe historical C results as new tests.
- Commit each completed stage separately. Keep raw recordings and generated
  firmware under ignored build paths; retain compact reproducible evidence.

## Ordered work

The original QMF cycle below is complete. Lower rates and external SPI input
have since been implemented/admitted in [LOW_RATES.md](LOW_RATES.md) and
[SPI_FLASH.md](SPI_FLASH.md). Current speed work uses measured hot paths;
[WB_NOISE_SPEED.md](WB_NOISE_SPEED.md) records exact seven-product noise
arithmetic and the next opportunity to remove duplicate noise generation.
That opportunity is now complete in [WB_NOISE_REUSE.md](WB_NOISE_REUSE.md):
WB3.95 speech is 75.60% CPU, with exact output and a complete +8% IRQ run.
The remaining candidates include the weighted vocoder mean and bounded HB1
gain division; their proof obligations and numeric domains are recorded there.
The broader speed objective remains open while useful candidates exist.

1. **Current baseline and profiling.** Correct the WB profiler to accumulate
   instruction cycles only inside measured frame intervals, across all streams.
   Run both ASM rates on existing reference-bound corpora; identify QMF, NB/HB
   IIR, LPC and control costs. Freeze source, tool, input and output hashes.
2. **Exact hot-path optimization.** Start with the dominant measured kernel.
   Explore register/load reuse and constant arithmetic without changing the
   filter. Test full-scale, clipping, negative rounding, state and alias cases.
   Keep only useful measured changes; record rejected alternatives too.
3. **Integration and timing.** Run both complete WB corpora and continuous-history
   PWM checks with interrupts active. Compare per-stream means/maxima, memory
   and queue margin. Preserve the C source/reference contract.
4. **Quality budget and next gate.** Assess the measured spare cycles before
   extending QMF precision/taps. A different QMF must be compared against full
   Xiph synthesis and listened to on Russian/English speech plus non-speech;
   it needs a separate oracle/profile and fresh timing admission. HB2, higher
   rates and 32 kHz require their own resource/quality work and are not implied
   by an exact optimization of the current HB1 profile.

Record completed work, measurements, reproduction and remaining candidates in
the accompanying report/documentation. Add reusable measured techniques to
`docs/avr-asm-cookbook/`.

## Baseline completed, 2026-10-30

Revision `22e50e01c9595b62e78fc2b6c0e454c51bbe7dfc`; AVR GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax` plus existing per-function options;
avr8js 0.21.1, no IRQ in the decoder mailbox. Each rate checks 10,563
sequential frames plus 17 first-frame reset checks, exactly against its
existing compact-profile PCM oracle.

| ASM profile | Mean / max frame cycles | Flash / static / stack bytes |
| --- | ---: | ---: |
| WB9.8 | 238611.592 / 245412 | 17072 / 1279 / 180 |
| WB12.8 | 241085.577 / 246660 | 19870 / 1287 / 192 |

QMF self cycles are 52425.6 / 52429.7 per frame (21.97% / 21.75%). The
NB/HB IIR pair costs about 42% combined. QMF offers two small exact changes
without adding state or complicating coefficient-age handling: biased
half-input arithmetic and first-tap accumulator initialization.

`reports/wb-qmf-before-*.json` and `wb-qmf-profile-before-*.json` retain the
full per-stream and self-symbol-cycle data. The corrected profiler excludes
startup/reset, accumulates all streams, and asserts that attributed cycles
sum to the complete measured frame intervals.

The extended QMF unit driver also passes the unchanged kernel: 2244 blocks,
179520 output words, 92 clipping/rounding boundary blocks, all signed16 input
values in both channels, alternating permitted alias, read-only inputs,
guards and 2244 callee-saved/r1 return checks. See `wb-qmf-unit-before.json`.

## Exact optimization completed

Biased half-input arithmetic, a shared bias constant and first-tap
initialization save exactly 2560 cycles/frame and 64 B Flash in both modes.
The fresh full-corpus profiles attribute the entire reduction to QMF.
All 21126 sequential decoder frames and 34 reset checks preserve signed16
PCM; direct QMF tests also preserve mirrored state, alias and ABI.
SRAM and peak stack do not change. See [WB_QMF.md](WB_QMF.md) and the cookbook.

## Integration and timing completed

Both full-history ASM players pass all 21126 frames with exact signed16/PWM,
zero underruns and 8% extra foreground work. Minimum queues improve 6 -> 7
and 5 -> 6 samples. Two Flash-fed 128-frame production slices also pass at
8% load. Five final images rebuild identically; the source-bound audit checks
the preserved 48 C/header files against prior evidence without rerunning C.
Ready RAM and embedded Flash do not measure external delivery latency or a
physical board. See `reports/wb-qmf-admission.json` and `WB_QMF.md`.

## Quality budget assessed; first improvement cycle complete

The [offline QMF screen](WB_QMF_BUDGET.md) compares 16/20/24/32 taps against
the full Xiph coefficient response. It identifies a 24-tap Q7 profile as the
next bounded quality experiment, requiring more history and a retained cursor.
It is not implemented or admitted; the present optimization preserves the
existing sound exactly. More work remains on real-board/external-transport
timing and any intentional quality or bitrate extension.

Lower rates are a separate extension, not an effect of speeding up QMF.
The vendored mode map and [Xiph WB manual](https://www.speex.org/docs/manual/speex-manual/node11.html)
define 7.75 kbit/s as NB submode 2 plus the already supported HB1. Supporting
NB5.95 first could therefore enable a future WB7.75 profile; it still needs
implementation, independent PCM evidence and target timing admission. The
AVR decoder at that original assessment accepted only NB8/NB11 and WB9.8/WB12.8;
the later lower-rate implementation is documented above.

### Lower-rate reuse assessment

These are source-inspection conclusions, not implemented support or a measured
Flash forecast. The vendored `modes.c` defines:

| Proposed pair | Lower-band additions | Raw new innovation table |
| --- | --- | ---: |
| NB5.95 / WB7.75 | Frame pitch, per-subframe 3-tap gain, 4-bit innovation indices; same 4x10 geometry | `exc_10_16_table`, 160 B |
| NB3.95 / WB5.75 | Forced pitch/gain, 2x20 innovation geometry | `exc_20_32_table`, 640 B |
| NB2.15 / WB3.95 | Noise excitation, vocoder synthesis and additional persistent state | Different algorithm, not just a table |

LBR LSP codebooks, LSP/LPC conversion, IIR, excitation history, QMF, HB1 LPC
and output queue can remain shared. The cheapest first pair uses the existing
3-tap gain table too. Its parsing, gain scaling, codebook bounds and HB folding
reconstruction still require new code and reference checks; the raw 160 B
table is not the total firmware increase.

Prefer a build-time optional NB2 extension with mode selection once per frame
or vector, retaining the existing fast inner kernels. Share a table-addressed
ten-sample operation or larger vector routine where register/call cost allows;
do not instantiate a complete decoder per rate or generalize every sample's
hot loop. Recheck scale bounds before reusing the current signed24 ASM kernels.
Keep a selectable C equivalent. Compare final Flash, stack, cycles, PCM and
active-IRQ output against the current profile before admitting any extension.
