# Wideband improvement plan

Target: ATmega328P, 16 MHz, 2 KB SRAM; compact WB9.8/WB12.8, mono 16 kHz.
The explicitly enabled AVR ASM backend is the performance target. Retain
the portable, explicitly selectable C fallback and existing backend selection.

## Acceptance rules

- Separate exact speed changes from intentional synthesis/quality changes.
- Exact changes must preserve every signed16 output, reset, history, permitted
  QMF alias, saturation and rounding. Keep existing independent oracles.
- Measure cycles, Flash, static SRAM and peak stack with the same pinned
  compiler/options and input bytes before/after. Reject unexplained regressions.
- Recheck continuous output with production timers/interrupts and queue code,
  including 8% additional foreground work. Ready RAM packets do not establish
  storage/serial latency or physical-board timing.
- Do not rerun the excluded Speex C performance suite. When C sources and
  dependencies remain unchanged, bind their previous reference evidence by
  hashes; do not describe historical C results as new tests.
- Commit each completed stage separately. Keep raw recordings and generated
  firmware under ignored build paths; retain compact reproducible evidence.

## Ordered work

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
