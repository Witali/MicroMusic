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

## Runtime-selected exact Q14 paths

After validating a file coefficient, the AVR25 prepared filter tags four
frequent values (7800, 13094, 13926, 16383). These select exact shared
shift/add sequences, including the near-unity identity
`floor(16383*s/16384) = s - ceil(s/16384)`. All other valid coefficients
still use the general runtime kernel. The tags are internal decoder state;
the file format and its stored parameters do not change. The C fallback
keeps the ordinary mathematical product and floor.

This trades 268 B Flash for 19–29 cycles/sample on the public filter cases
and 72 on the heaviest synthetic filter pair. Other cases keep their old
timing. Static RAM, peak stack and IRQ cost do not grow. `filter-measurements.json`
records all 44 IRQ comparisons with the mirrored intermediate. Every mean
and peak is equal or faster; decoded PWM and compressed data are exact.
All 22 8 kHz cases pass, while 12 kHz still admits only 9/22. The total
12 kHz underrun count falls from 21726 at task start to 10745; neither
the lower mean nor this reduction is a claim of complete real-time support.

The combined single-stream program is 3997–3998 B (3.903–3.904 KiB),
334 B more than task start. The largest required full image is 5878 B
(5.740 KiB), within 6.5 KiB and the 6012-byte USB application region.
Static RAM/peak stack are 436/27 B. Nano's 22 images remain byte-identical.
Worst complete producer plus IRQ falls from 1664.088 to 1540.084 cycles
per sample, still above the 1336-cycle 12 kHz budget.

`filter-arithmetic.json` and its build record bind the integrated headers.
Actual AVR ASM passes 966663 cases: every signed16 state for 13 coefficients,
then seven boundary states for all 16385 valid coefficients. AVR C passes
the 114695 coefficient-domain cases; portable C passes all 966663 against
independent explicit floor division. IRQ, stack and callee-saved/r1 checks
pass; selecting the generic architecture yields the same binary as C.
Reproduce with Node on PATH and the installed AVR/host toolchain:

```
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_filter.py build/filter-proof --wsl Ubuntu
```

## Actual wideband results

`wideband-quality.json` records eight distinct 1.28-second source excerpts,
four Russian and four English, at original 44.1/48 kHz. The minimum measured
source energy from 4.2 to 7.8 kHz is 0.864%; its median is 11.254%.
These sources really contain an upper band. Actual resampling precedes
analysis for all 32 encodes: eight excerpts × P4/P6 × 12/16 kHz. All match
portable C PCM/PWM. Source licensing and hashes were checked against the
local original-source manifests; source media and individual attribution
remain private local test artifacts, not published codec assets.

The upper band is considered by LPC analysis, but not reconstructed as
accurately as the main speech band. Median 4–6 kHz SER at 12 kHz is
2.361/2.933 dB for P4/P6; at 16 kHz the 6–8 kHz medians are only
0.793/1.430 dB. STOI does not evaluate that highest band. This experiment
does not tune the encoder or claim improved quality.

`wideband-irq.json` compares task start with the combined optimized firmware
on all 16 genuinely encoded 12 kHz streams. These are additional held-out
loads, not header-retagged old 8 kHz audio. Every genuine normalized PWM
sample equals the unchanged model/C output (245760 samples per set).
The separate raw-C comparison is in `wideband-c-model.json`.

Admission improves from 0/16 to 4/16; total underruns fall from 10752 to
1095. Complete producer plus filled-queue IRQ costs 1247.982–1359.164
cycles/sample. Twelve cases still miss deadlines, including cases with a
mean below 1336 because of bursts. Real wideband 16 kHz was checked for
encoding/reference output only; it is not admitted for Tiny playback.

## Rejected directions

Measured pulse-gap memory-constraint alternatives add 1.10–5.29 cycles per
sample and 2–4 B on four representative controls, including real wideband.
A FIFO64 screen before the mirrored history reduces some burst misses but
does not address over-budget means. Neither is selected.

Increasing FIFO32 startup prefill from 24 to 31 leaves all 16 wideband
underrun counts, active timing, memory and admission results unchanged.
It cannot absorb later bursts after the queue has already refilled.
Outlining cold timer startup saves one foreground cycle for 8 B more code
on four controls; that small trade is not selected either.

Cached LPC odd multiples and integral24 accumulation were reviewed but not
implemented or measured: table loads/preparation erase the expected savings,
and packing each Q4 product into integral24 requires more work than its saved
byte subtraction. These are cost analyses, not measured portability claims.
