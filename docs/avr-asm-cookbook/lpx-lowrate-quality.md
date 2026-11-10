# LPX low-rate quality: exact playback and independent error checks

Applicable playback target: ATtiny88/AVR25 without MUL, 16 MHz, avr-g++ 7.3,
the standalone reserved-register ISR ABI and SRAM512 profile. Arithmetic ASM
requires explicit enable; the portable C backend remains selectable on AVR too.
The techniques below concern offline search and validation, not a measured new
assembly kernel. The current three-profile reader's size/IRQ admission is in
[the v9 notes](lpx-v9.md#shared-sparse80-reader-and-pulse-gaps-2026-11-10).

## Exact output does not establish cleaner sound

The public Chego tuning example has 9831 samples at 8 kHz. A local-neighbor
experiment changed four sparse80 pulse fields after filter refinement. Both
files used 297 bytes, and the new output matched the independent C receiver
and complete AVR/IRQ playback with no underruns. Its full image used 5902 B
(about 5.76 KiB), observed stack margin was 11 B, and mean active cost including
IRQ was about 1547 cycles/sample. Those checks establish implementation and
timing correctness, not quality.

Listening rejected the local variant: its rasp became higher in frequency and
more noticeable despite lower waveform/joint-proxy error. A source-referenced
80-ms Hann/20-ms-hop analysis of complete windows found error power increases
of about 0.67% at 1.5–2.5 kHz and 0.30% at 2.5–4 kHz versus the predecessor.
The lower bands improved. Independent exploratory envelope measurements also
found increased upper-band modulation error; these are uncalibrated diagnostics,
not an audibility model. The candidate is not admitted as a quality improvement.

Instrumented integer-model checks found no excitation, LPC, deemphasis or
output-Q14 saturation in this phrase; its PCM16 matched native C and its PWM
matched complete AVR playback exactly.
Reducing clipping alone therefore does not explain this particular result.

## Protect hardware-domain bands and short tails

For further proposals, check actual PWM samples as well as PCM16. Require
fixed source-referenced high-band error totals and source-relative burst maxima
to stay within their predecessor's bounds. The experimental pulse tool uses
fixed 1.5–2.5/2.5–4 kHz bands, 80-ms frames and 20-ms hops, with duration-weighted
totals and every partial-tail window. A half-sample Hann leaves even one/two
remaining samples observable. Missing or mismatched window rows fail closed.

These bounds now reject the known tuning failure. That is a regression check,
not independent perceptual validation. Keep the search opt-in, retain the exact
predecessor, and count a PCM-only change with identical PWM bytes separately.
For corpus evidence, protect the whole recording after segmentation and report
whole-record votes, material numerical proxies and listening results separately.
[Search contracts](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/SPARSE80_QUALITY.md).

## Rounded feedback: a separate untested hypothesis

The existing Q4 predictor is `floor((gain * history + 8) / 16)`. With gain 14,
history 4 maps to 4 and history -3 maps to -3. Thus small nonzero fixed points
exist even without a new innovation. This arithmetic observation is not a
diagnosis of the phrase's rasp: the encoder may use those states deliberately.

Do not silently change rounding or leak those states away in an existing
format. A different feedback law needs explicit format selection, a matching
C reference, re-encoding, quality checks and complete active-IRQ measurements.
Likewise, changing a seven-bit pulse codebook preserves its nominal data width
but does not establish better quality or a fit in the remaining Flash budget.

All observations and codebook ideas here are original project work. No external
assembly implementation was adapted. Unmeasured format/rounding ideas remain
separate from the admitted decoder and published audio.
