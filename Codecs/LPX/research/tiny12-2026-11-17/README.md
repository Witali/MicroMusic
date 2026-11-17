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
