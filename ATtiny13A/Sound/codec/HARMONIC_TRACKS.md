# Strongest-partial trajectories and explicit tolerances

`HarmonicTrackObjective(reference, sr=7500, max_tracks=10)` caches the original
recording's strongest local spectral peaks at every time. They are not the
first ten multiples of an estimated fundamental. A 1024-point Hann STFT with
128-sample hop provides frequency/time samples; log-parabolic interpolation
estimates sub-bin frequency and amplitude. The FFT can be increased, never
reduced below 1024. Increasing it trades time resolution for frequency detail.

The original and candidate receive the same 70 Hz highpass and one global RMS
match. Every sample and its time position is preserved. Per-frame or per-band
normalization would conceal amplitude-envelope errors and is not used.
Silence is handled separately so an extra tone against silence is not scaled
away.

Track IDs follow predicted frequency rather than amplitude rank. Frequency
prediction can bridge short gaps and resolvable crossings. Unresolved peaks
cannot be separated by interpolation; their disappearance remains measurable.
At most ten peaks are retained at each time, although new IDs can be born
throughout a recording. Noise peaks are also eligible. This model measures
strongest partials, not all broadband power; the full spectrogram objective
must remain a companion diagnostic.

Original/candidate peaks are assigned one-to-one at the same time. The fixed
physical assignment gate is 100 cents, with a two-bin frequency floor. At the
default FFT that floor is 14.6484 Hz. This can exceed 100 cents at low
frequencies and must not be described as 100-cent measurement accuracy.
Assignment includes a continuity preference. Motion comparison follows the
same original ID even when candidate IDs fragment; an additional continuity
break penalty discourages such fragmentation.

## API and loss

`evaluate(candidate)` returns finite scalar metrics:

- `frequency_error_cents`, `frequency_error_hz`, `level_error_db`: matched
  partials' absolute errors, weighted by original partial power.
- `frequency_error_p95_cents`, `frequency_error_p95_hz`,
  `level_error_p95_db`: corresponding power-weighted 95th percentiles.
- `missing_reference_energy`: unmatched original partial power divided by
  total selected original partial power.
- `extra_candidate_energy`: unmatched output partial power divided by the
  larger of original/output selected partial powers.
- `weighted_match_rate`: matched original power divided by total original
  power. Both silent gives one; an unmatched non-silent output gives zero.
- `continuity_break_rate`: power-weighted candidate-ID changes on the same
  original trajectory, among comparisons with an eligible predecessor.
- `frequency_trajectory_error`: 75% tolerance-normalized frequency error plus
  25% temporal change of signed error along the same original trajectory.
- `level_error`: mean absolute dB error divided by amplitude tolerance.
- `harmonic_track_loss`: `0.35*frequency_trajectory_error + 0.2*level_error +
  0.3*missing_reference_energy + 0.15*extra_candidate_energy +
  0.05*continuity_break_rate`.

Default loss tolerances are 50 cents, zero Hz floor and 3 dB. Configure them
with `frequency_tolerance_cents`, `frequency_tolerance_hz` and
`amplitude_tolerance_db`. `with_tolerances(...)` shares the frozen original
tracks without extracting them again. The absolute metrics and assignment
gates do not change when loss tolerances change. A larger tolerance therefore
does not silently turn missing/extra energy into a valid match.

For size/quality control, minimize actual packed bytes while enforcing the
requested **absolute** error limits and separate coverage/missing/extra
limits. A smaller normalized loss by itself proves neither a bound nor a
smaller firmware. Matched frequency/level errors exclude missing tracks;
their zero when no track matches is not evidence of accuracy. Always inspect
coverage and missing energy alongside them.

`reference_tracks` caches times and frame-by-amplitude-rank arrays:
`frequency_hz`, `amplitude`, `track_id`, `count`. Absent frequencies are NaN,
amplitudes zero, IDs -1. `extract(candidate)` returns corresponding output
tracks after the shared level treatment. `details(candidate)` adds matched
original/output IDs, frequencies, amplitudes, absolute errors and original
power for every same-time match.

## Inspection

```
python tools/compare-harmonic-tracks.py \
  --reference path/to/original.wav \
  --candidate "Previous=path/to/old.wav" \
  --candidate "Candidate=path/to/actual-avr.raw" \
  --output build/harmonic-comparison
```

The RAW reader accepts one exact phrase or a phrase followed by twice its
length of verified midpoint silence. WAV sample rate, channels and duration
must match. The PNG uses shared frequency and amplitude axes, ID-colored
original and matched paths, red missing original peaks and orange extra output
peaks. JSON retains the exact trajectories, assignments, scalar diagnostics,
configuration and source hashes. Plotting uses the same objective data as
optimization, rather than another peak detector.

`python tools/test-harmonic-tracks.py` covers strongest-ten selection,
amplitude rank swaps, chirps/crossings, short gaps, fixed detuning, missing and
extra partials, octave replacement, silence/noise, global level invariance,
tolerance independence and candidate-ID fragmentation. The physical STFT
resolution limits remain explicit.
