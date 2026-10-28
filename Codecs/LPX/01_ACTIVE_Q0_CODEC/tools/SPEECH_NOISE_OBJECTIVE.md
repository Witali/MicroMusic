# Source-bound harmonic and noise-shape criterion

`NoiseObjective(reference, source_periods)` from `speech_noise_objective.py`
provides:

- `noise(pcm)` or `noise.score(pcm)`: a finite nonnegative scalar in `[0,1]`.
- `noise.summary(pcm)`: a JSON-safe summary, with explicit missing/unassessed counts.
- `noise.describe()`: fixed geometry, interpretation, scope and suggested weight.
- `noise.voice_objective`: the accompanying owned `VoiceObjective`, reusable by
  the controller instead of constructing a second voice context.

The reference is full-length integer PCM16. `source_periods` follows the existing
voice objective: one period or NaN per complete 640-sample window at 160-sample
hops, or `None` when source pitch is unassessed. Source PCM, periods, masks and
feature arrays are owned/read-only snapshots. No candidate pitch detector is
called. Input gain, samples, rate and timing are never modified.

## Features and bounded score

The existing voice objective's positive-frequency Hann periodogram is shared.
For each source-confident period, bins near its harmonics through 3,800 Hz are
grouped by harmonic number. The half-width is the smaller of 1.5 FFT bins and
source F0/4, preserving gaps between low-F0 harmonic groups. Remaining positive
frequency bins stay separate, including Nyquist. DC, output gain and phase
remain responsibilities of the waveform/voice criteria.

Group powers are divided by total power only inside analysis. Their square roots
form a probability-vector representation. Squared Hellinger distance measures
harmonic-envelope and fine off-harmonic shape change. The absolute difference
between source and candidate off-harmonic fractions measures balance. A voiced
frame's score is the mean of these two terms; each is bounded by one.

**The source's noise is the target.** Removing natural breath/aspiration and
adding artificial noise both differ from that target. This is not a rule to
minimize all off-harmonic energy. It is also not calibrated HNR, roughness,
speaker identity or a true-F0 estimator. This FFT grouping is a new reusable
feature; its numbers are not interchangeable with the exploratory QR harmonic
residual in the earlier roughness probe.

Unknown-pitch and partial windows use fine spectral Hellinger distance without
guessing harmonic structure. Vanished output for a nonzero source spectrum pays
one and stays in the denominator. Silent source windows penalize newly injected
AC power, capped at one with a one-PCM-count RMS floor. Fewer than four samples
have no reliable spectral assessment: their score is neutral and their unassessed
count is explicit; the voice waveform scorer still covers those samples.

Frame scores are averaged into `[0,1]`. A fixed external weight of one is an
initial dimensionless choice, comparable in bounds with the existing spectral
criterion rather than an unbounded dB quantity. It is not fitted to a target clip
or calibrated as perceived quality. The parent controller can combine
`noise.voice_objective(pcm) + noise(pcm)` while retaining complete PCM/PWM metric,
pitch-count and clipping gates. This module does not change those gates.

## PCM/PWM and honest limits

Score native PCM and fixed PWM separately. Construct the matching reference
object for each domain and keep the source period mask fixed if supplied.
If direct source PWM is neutral, its harmonic balance is unavailable even if
the original PCM has a reliable period. A zero noise-shape score in that domain
is not evidence that sub-LSB pitch survived; summaries state the unavailable
assessment. Level/phase changes can preserve this normalized shape, so waveform
criteria remain necessary. Several octave errors are detectable through changed
harmonic groups, but a single spectral proxy cannot resolve every ambiguity.

All FFT work uses batches of at most 64 source windows. Reference feature storage
is linear in the number of windows. No firmware code, format, assembly backend
or playback default changes. No target/corpus fits or audibility claim were added
while developing this component.

Nine synthetic groups cover quiet self/collapse/octave controls, natural-breath
removal/addition, source-mask immutability, unknown source pitch, silence/noise
injection, short windows, PCM-to-neutral-PWM loss, original-level/phase limits,
input ownership and invalid values. An independent direct FFT formula checks the
shared periodogram, including partial tails; all existing voice objective and
voice diagnostic tests remain passing.
