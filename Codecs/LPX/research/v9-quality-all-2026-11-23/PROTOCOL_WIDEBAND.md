# Revised prospective wideband study

This addendum supersedes the primary matrix and hard waveform-error admission
in `PROTOCOL.md`. The earlier 24-job public v1 pilot remains unchanged evidence:
all candidate outputs equalled the incumbent, with no measured quality benefit.
Its protocol, targets, source snapshots and receipts remain frozen privately.

## Source cohort and split

The primary matrix is 24 complete utterances, each 4–8 seconds, from genuine
original sources sampled at 16 kHz or higher. Use 12 official FLEURS cases
(six Russian, six English) and 12 official VCTK cases, with LibriSpeech as a
documented acquisition fallback if necessary. FLEURS uses two tuning/train
and four held-out/test cases per language. VCTK uses four tuning and eight
held-out cases from distinct source speakers. This gives eight tuning and
16 held-out cases; it is not a claim of 24 independent speakers across corpora.

Eligibility and ordering depend only on the original source, before viewing
codec outputs. Preserve whole utterances, original level, source order and
private provenance. Prepare 16 kHz directly from the original sample rate.
At least one 1 kHz band at or above 4 kHz must exceed 1e-4 of total source
spectral power under the fixed 512/256 analysis below. Select at least eight
cases with a supported band at or above 6 kHz if the acquired reserve permits,
using deterministic replacement within the same corpus/language/split group.
Record an unmet quota honestly; never replace cases because of codec output.

Primary settings are P4/P6 at 12/16 kHz, 96 jobs per encoder. Prepare each
target directly from native source PCM, with no 8 kHz intermediate. The old
27-case corpus is a separate narrowband regression: P4/P6 and strict 3/8 kbit/s
at 8 kHz, 108 jobs. Do not run the superseded 216-job resampled high-rate
matrix or present it as genuine source high-band evidence. The already
approved original 44.1 kHz phrase (four settings) and continuous 128001-sample
Long reference (two profiles) remain separate ancillary controls.

## Magnitude and time fidelity

The source contains the desired noisy components. It is not a noisy input
to denoise. Noise does not require sample-identical phase. Waveform SSE and
complex spectral residual remain diagnostics, rather than absolute admission
floors. The principal independent measurements are native full-band magnitude
spectrogram residual and changes of that magnitude spectrogram between adjacent
frames, with source-referenced high-band envelope and onset diagnostics.
Speech intelligibility, source-frozen period observations, clipping, complete
sample count and the same byte budget remain separate safety measurements.
Do not present an objective metric change as an audible-quality percentage.

Use exactly the previously frozen symmetric Hann 512-sample windows, 256-sample
hop, starts -256, 0, 256, ... below the sample count, zero padding and 1 kHz
physical bins. Retain every frequency band through the actual Nyquist limit,
including quiet or unsupported source bands. One-sided FFT weights and common
`512*sum(window^2)` normalization are fixed. Report per-frame source/output
band power, squared complex residual, squared magnitude residual, squared RMS
envelope difference and positive envelope-onset difference. Also report squared
residual of adjacent-frame magnitude changes. Transitions are compared at their
original time; no output-dependent delay, gain, cropping or spectral alignment.

## Source-only noisy/unvoiced diagnostic

This mask is a heuristic diagnostic, not a phoneme label or ground-truth VAD.
A frame is active when its window-normalized source RMS is at least 0.5 PCM16
units. For classification only, subtract the frame mean. Compute spectral
flatness across FFT bins at or above 100 Hz. Compute peak positive normalized
autocorrelation across integer lags for 50–800 Hz, with each lag normalized by
the energies of its two overlapping vectors. Classify an active frame as
noisy/unvoiced when flatness is at least 0.2 or peak autocorrelation is below
0.6. A magnitude-change transition belongs to this subset if either adjacent
source frame belongs. The rule is frozen before held-out codec outputs.

Report subset counts and errors for every band, plus fixed physical high-band
sums at or above 3, 4 and 6 kHz when supported by the target sample rate.
Framewise records remain private because they can fingerprint an input.
Public evidence contains anonymous cohort sums and fixed denominators only.

## Run admission

Before launching the full matrix, freeze the revised encoder and complete a
new public tuning pilot with useful quality evidence and runtime. The earlier
v1 result is a safety result, not an improvement. Exact production objective
and safety guards must be frozen before held-out outputs. Retain both the raw
candidate and exact incumbent; distinguish selection from independent measured
improvement. Optional decoded-output normalization remains a separate pending
matrix until its format and implementation are validated.

The V2 selection formula is frozen before the new tuning pilot. Define a
per-bin magnitude residual r=|X|-|Y|. The temporal residual is the difference
of adjacent residuals, starting only at the second frame. Apply the same
window-power normalization as magnitude residual, including the full frame
count in the denominator. A balanced error is the mean of each band's error
power divided by `max(source_band_power,total_source_power*1e-4)`; a silent
source uses denominator one. Compute balanced magnitude and temporal errors
on both PCM/PWM paths. Neither may increase, and total normalized magnitude
error may not increase, with absolute tolerance 1e-12.

The selection score averages frozen-incumbent-relative losses across both
paths: balanced magnitude weight two, balanced temporal weight two, voice
weight one, noise weight one, full-rate waveform SSE weight one; additionally
include 1-STOI, source-period error and coarse spectral-shape error at weight
one each when the incumbent value is finite. Divide by the included weight.
A zero incumbent loss is an exact zero floor, without an epsilon denominator.
Voice/noise/period/shape reference equations use the existing source-frozen
8 kHz analysis after the pinned Octave-compatible antialiased conversion,
retaining double PCM16 units at 12/16 kHz. Independent reporting additionally
keeps actual-rate pitch and full-band noisy/time diagnostics.

Separate safety floors require valid STOI not to fall, source-period matches
not to fall, collapsed active frames not to rise, and PCM clipping not to
increase. Individual band retention and waveform SSE can trade off within
the frozen weighted score; report those tradeoffs explicitly. The exact
pre-change incumbent remains a candidate at its original complete byte cap.
