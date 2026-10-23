# Controlled frequency versus partial-level perturbations

This PC diagnostic changes either tracked partial frequencies or their
individual levels in the original recording. It is not a codec optimization,
an AVR implementation or a proof of subjective sound quality. It complements
same-budget codec parameter-weight experiments rather than replacing them.

The generic tool is `tools/probe-partial-error-effects.py`. It automatically
extracts the strongest <=10 partials at each time using the retained tracker.
Soft complex-STFT peak-cluster masks keep original phases and allocate each
bin at most once. A flat two-bin main-lobe region tapers to zero at three
bins. Every learned partial is reconstructed and the original minus their
sum becomes a separately retained residual. No speech interval or frequency
is selected by hand.

For frequency conditions, analytic partials receive phase modulation from
the integral of a signed cents-derived frequency offset. This changes phase
progression while preserving each analytic component's amplitude envelope.
For level conditions, the original component is multiplied by a real constant
gain. Its frequency is not explicitly moved. Signs alternate by fixed track
ID and remain unchanged through that trajectory. The residual and complete
sample count are preserved before common global level processing.

The identity control reconstructs the recording with maximum sample error
`1.3877787807814457e-17`; STOI and eSTOI are both 1.0. Pure resolved-tone tests
independently check ten-cent detuning with little level error and level changes
with little frequency error. Three tests pass.

## Vinni result

The complete 22272-sample canonical 7500 Hz reference has WAV SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.

| Nominal intervention | Measured mean frequency error, cents | Measured mean level error, dB | STOI | eSTOI |
| --- | ---: | ---: | ---: | ---: |
| Identity | ~0 | ~0 | 1.000000 | 1.000000 |
| Frequency +/-10 cents | 13.851 | 1.021 | 0.933488 | 0.884432 |
| Frequency +/-25 cents | 26.635 | 1.347 | 0.933437 | 0.879015 |
| Frequency +/-50 cents | 46.906 | 2.341 | 0.926977 | 0.866550 |
| Levels +/-1 dB | 1.549 | 0.922 | 0.998958 | 0.997689 |
| Levels +/-3 dB | 2.505 | 2.668 | 0.991034 | 0.980859 |
| Levels +/-6 dB | 5.101 | 5.390 | 0.967433 | 0.934476 |

The constructed frequency perturbations harm these objective scores more
than these particular level perturbations. This does **not** establish a
universal ratio of frequency versus intensity importance. Cents and decibels
are different intervention units; nominal severities are not perceptually
equated. The largest frequency intervention is also not monotonically worse
on every score.

Finite STFT separation and recombining overlapping partials/residual produce
measurable cross-effects: the frequency interventions also alter measured
peak levels, while level interventions slightly alter measured peak positions
and rankings. Those cross-effects are reported rather than assumed absent.
STOI/eSTOI measure intelligibility-related behavior, not naturalness ratings.
The identity tracking loss has a tiny nonzero continuity term from numerical
sensitivity of weak-peak association, despite effectively exact waveform
identity; its frequency/level and full-spectrogram errors are negligible.

The report retains all six conditions plus the identity control, complete
spectrogram/track metrics, deterministic eSTOI, runtime and source hashes.
No compressed-size claim is made, and no original or generated audio is
stored in this research directory.

## Reproduction and listening

```
python tools/probe-partial-error-effects.py \
  --reference path/to/original.wav \
  --output build/partial-error-effects/vinni
python tools/test-partial-error-effects.py
```

Generated FLOAT WAVs retain each full raw intervention. `comparison.wav` is
original, identity reconstruction, +/-25-cent frequency condition, +/-3-dB
level condition. All four receive the same 70 Hz highpass, one global RMS
match, a common peak scale and 0.3-second gaps. `partial-error-effects.png`
shows measured cross-effects and objective scores; `spectrograms.png` uses
shared axes and a common original-referenced dB scale.
