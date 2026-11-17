# ATtiny88 12 kHz optimization experiment

Work starts from `66e3d93499b6df060f8a5c7cdcb133d682dc3106` on
`codex/lpx-tiny88-12k`. Measurements use AVR-GCC 7.3.0, GNU AVR ABI,
simavr 1.6 and the project's ATtiny88 peripheral model, at 16 MHz.
They are simulator results, not physical-board measurements.

Nominal 12 kHz uses the user-selected compact fixed timer divider: 1336
cycles/sample, or 11976.048 Hz. The 8 kHz compatibility control uses 2000
cycles/sample. FIFO size/prefill remain 32/24. C arithmetic is explicitly
selectable on AVR; the desktop floating-point synthesis is unchanged.

## Gain loop

The foreground PWM gain routine handles unity directly and groups its seven
remaining multiply rounds into one initial round and two groups of three.
Its clipping uses the carry-derived rail mask. The runtime gain still comes
from the file's separate ROM normalization pass; no recording constants or
sound data are compiled into the arithmetic.

Compared with the starting source, the complete Tiny program grows 22 B to
3685–3686 B, excluding audio. Static SRAM/peak stack remain 418/27 B.
The foreground saves 59 cycles for unity gain and 14–15 for other gains.
All 22 workloads at both timer rates retain exact decoded PWM; all 22 at
8 kHz also retain exact complete output and zero underruns. At 12 kHz the
admitted count remains 9/22: this change alone does not meet the goal.
Underruns never increase. The 22 Nano controls remain binary-identical,
including their audio, at 3056–3057 B excluding audio.

`gain-measurements.json` retains the paired 44 interrupt-active runs;
`gain-transition.json` binds their source hashes. `gain-arithmetic.json`
records all 32768 duty/gain combinations for each of four C/ASM and
Tiny/Mega selections, with interrupts, ABI preservation and r1 checks.
The retained reproducer is `tests/verify_pwm_gain.py` in the active codec.

## Exact output when a deadline is missed

The simulator now saves a second PWM stream using FIFO occupancy at IRQ
entry as its validity flag. It keeps real duty128 samples and omits only
inserted underrun samples. Replaying all 44 old and optimized ELFs leaves
every original timing field and complete output byte unchanged. All genuine
samples equal the independent C reference, including 113098 duty128 samples
in the starting set. The old admission checks remain mandatory: valid-stream
equality never excuses a missed deadline.

## Required wideband checks

The old WebUI originals are only 7.5/8 kHz; resampling them cannot test a new
upper band. Additional checks use eight actual 44.1/48 kHz source excerpts,
with measurable energy above 4 kHz, resampled before LPC analysis. Both P4
and P6 are encoded at 12 and 16 kHz. These are deliberately selected stress
excerpts, not a representative quality study. Timing and upper-band quality
are reported separately. No quality improvement is claimed for an exact
decoder optimization.

## LPC accumulation and mirrored history

The AVR25 v9 loop biases every signed24 product by 2^23 and compensates ten
biases once in the accumulator. A zero history sample skips coefficient
loads. Other compact versions and the explicit C backend retain their
arithmetic. The linear loop alone adds 16 B and saves 14.86–16 cycles/sample.

The universal Tiny builder then selects the existing 20-word mirrored LPC
history layout for both C and ASM. A single cursor derived from subPos
consumes ten reverse-history words; only the new sample is written twice.
No separate cursor or stack byte is added. This removes history shifts and
saves another 21.31–21.41 cycles/sample, for 28 B Flash and 18 B static RAM.
The Nano layout is unchanged.

Together with the gain change, the player is 3729–3730 B excluding audio
(+66 B against task start), with 436 B static RAM and at most 27 B stack:
49 B measured margin in 512 B. The largest of the required 22 images is
5610 B including sound. All 44 genuine PWM streams are exact, all 22 8 kHz
outputs remain uninterrupted and exact, and all 12 kHz underrun counts
decrease or stay zero. The 12 kHz admission count is still 9/22.

`lpc-measurements.json` compares the combined player with task start, not
the gain-only intermediate. Every mean and peak improves against task
start. Against the gain-only intermediate, all active CPU peaks improve;
the all-pairs wall-clock producer peak increases 5 cycles because of IRQ
phase, while remaining below task start. Against the linear biased loop,
the mirror's all-pairs active peak rises 9 cycles, also below task start.
These intermediate peak costs are included in the comparison scope.

`lpc-arithmetic.json` records 44662 linear and 41280 mirrored cases per C/ASM
backend under live IRQ, with zero arithmetic, bounds or r1 errors. The
mirrored probe covers all 20 phases and chained wrap/saturation transitions.
Reproduce on Linux/WSL with:

```
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_lpc.py --fixtures both
```

An independent native lifecycle comparison checks 2170 operations across
22 full workloads and 26 short streams, including copy, assignment, reset,
restart and EOF/error state. Linear and mirrored histories produce the
same digest (`lpc-lifecycle.json`).

Two complete Tiny controls also select C arithmetic with the mirrored layout
and live ASM IRQ, at 8/12 kHz. All 22631 genuine samples match; static SRAM
437 B plus peak stack 50 B fits 512 B. These slower C controls are output and
fallback checks, not real-time admissions (`lpc-c-controls.json`). Seven
actual-rate frontend tests and the fixed/desktop-float controls also pass.
