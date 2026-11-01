# Diagnose voice-character loss without guessing a decoded pitch

The new host-only diagnostic observes **77 source candidate-period windows and
zero paired decoded candidate-period windows** in each existing A/B PCM and PWM
example. It does not measure a reliable decoded fundamental or prove a downward
octave shift. This evidence supports investigating lost periodic structure and
spectral shape, alongside the user's listening feedback.

This is the same complete 32,000-sample / four-second user-targeted pair. It is
now a diagnostic target, **not independent held-out validation for a new
encoder setting**. A/B remain near equal to one another. Their similarity does
not establish preservation of the pre-LPX source's character. No new audio was
encoded and no default, decoder, gain, sample rate or length changed here.

[Method, settings, interface and primary references](../../01_ACTIVE_Q0_CODEC/tools/VOICE_CHARACTER.md)
describe the direct bounded YIN-style measurement, fixed-source-period error
and coarse relative-power spectral descriptor. The defaults were selected from
algorithm/analytic synthetic requirements before this target inspection. The
80-ms windows advance by 20 ms and overlap; counts are not independent samples
or validated voiced labels. Source candidate-period median is about 202.53 Hz.

| Output | Paired / source period windows | Fixed-source-period error, mean | Coarse relative spectral shape error, mean dB |
| --- | ---: | ---: | ---: |
| Source against itself | 77 / 77 | 0.06060 | 0 |
| A native PCM16 | 0 / 77 | 0.57967 | 10.62328 |
| B native PCM16 | 0 / 77 | 0.58131 | 10.49468 |
| A fixed PWM | 0 / 77 | 0.95035 | 39.93465 |
| B fixed PWM | 0 / 77 | 0.95060 | 39.98729 |

The fixed-period comparison remains defined on the same source windows when
decoded tracking fails. Zero output pays a value of 1 rather than avoiding the
measurement. The spectral descriptor uses 24 coarse bands and factors out gain
only inside analysis; original level descriptors remain in
[summary.json](summary.json). It is neither a formant estimator nor a perceived
quality percentage. Its value can also reflect altered pitch. Missing paired
cents/hz remain null and the missing-period fraction is explicitly 1.0, never a
successful preservation score.

The pre-LPX source's complete RMS is about -61.49 dBFS. In 99 source-active
analysis windows the fixed PWM output falls below the stated diagnostic
resolution floor, whereas native PCM loses only three. This separates the
codec's PCM loss from the additional output quantization limitation. It does
not infer what an analog board or listener would hear.

Seven focused synthetic test groups pass. They independently use known sine
periods, PCM16 amplitudes down to 1, fractional search boundaries, deliberate
half/double pitch, same-period altered harmonics, zero/noise output, PWM
disappearance, exact source binding and immutable snapshots. The targeted
analysis uses the unchanged published A/B WAVs and source copy; no thresholds
were changed after looking at the target. The source-code hashes in the summary
bind the diagnostic and tests, not any media or firmware.

Input/output files, original paths, recording identities, media-derived hashes
and detailed listening records remain in ignored local storage. The new
diagnostic alone does not fix the encoder or establish corpus-wide preservation.
