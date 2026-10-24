# Measurements after the second listening comparison

The user reported that the last, rounded variant sounded slightly better and
requested measurements. This is tentative listening feedback for Vinni, not an
automatic change of the selected firmware or a claim about other recordings.

Measurements were freshly recomputed from the full original and all three
unchanged decoder outputs: 22272 samples at 7500 Hz, 2.9696 seconds. The actual
phrase PWM and phrase-plus-silence hashes match each retained three-engine build.
No new hardware run, encoding, resampling or time/phase alignment was performed.

| Measurement | Previous Q3 | Q3 + EEPROM | Last: rounded Q3 |
|---|---:|---:|---:|
| Full Flash bytes | 1024 | 1014 | 1024 |
| EEPROM bytes | 0 | 64 | 64 |
| Spectrogram error, lower better | .504357 | .503949 | .492822 |
| Top-ten matched level error, weighted mean dB | 7.382 | 7.305 | 5.617 |
| Top-ten matched level error, weighted p95 dB | 17.593 | 17.598 | 11.381 |
| Top-ten matched frequency error, weighted mean Hz | 11.037 | 10.672 | 10.738 |
| Top-ten matched frequency error, weighted p95 cents | 111.275 | 112.972 | 130.967 |
| Reference tracked energy matched | 82.72% | 83.06% | 83.65% |
| Weighted track continuity breaks | 35.31% | 30.63% | 13.35% |
| STOI, higher better | .838396 | .838637 | .830981 |
| eSTOI, higher better | .644611 | .645131 | .649758 |
| Raw output mean, full-scale amplitude +/-1 | +.073995 | +.074232 | -.000227 |
| Raw output RMS | .110910 | .111116 | .060649 |
| Raw waveform MSE | .030432 | .030487 | .022009 |
| PWM endpoint samples | 0 | 0 | 0 |

Spectral and matched-component rows use the established identical 70 Hz
highpass and one global RMS match per whole recording. The mean and RMS rows
use raw PWM without either adjustment. Thus the matched level improvement is
not a claim that the new firmware has the original absolute volume. Original
raw mean is -.000059 and RMS .129853. Raw-level (HP-only, no RMS match)
component mean errors are 13.811 / 13.769 / 12.120 dB respectively; both raw and
matched reports are retained.

Relative to previous Q3, rounding plus its refitted parameters reduces overall
spectrogram error by 2.29%, matched mean level error by 23.91%, matched p95
level error by 35.31%, and raw waveform MSE by 27.68%. Absolute DC magnitude
falls about 327 times. These are reductions of particular errors, not an
overall perceptual-quality percentage, and the experiment does not isolate
rounding from the extra data and parameter refit. MSE is phase sensitive and
its reduction partly reflects the removal of DC.

STOI drops .007416, while eSTOI rises .005148. Weighted p95 frequency error in
cents worsens even though the mean frequency error in Hz improves. The result
supports the observed spectral/level improvement but is not a uniform gain
across every metric. Strict frozen-baseline selection still rejects this
candidate because STOI is below its floor.

The strict **every selected component within 5 dB** requirement is still not
met. With level matching, reference-power violation fractions are 71.54%,
71.33% and 62.53%; missing selected peaks count as violations. Mean error
5.617 dB and p95 11.381 dB must not be reported as compliance with a 5 dB bound.
The full numerical output, input hashes, strict audits and source fingerprints
are in [listening-measurements.json](listening-measurements.json).

Recompute in the project Python environment:

```powershell
python tools/measure-speech-playback.py --reference web-player/audio/originals/vinni.wav --candidate Q3=build/lpc2-quality/vinni/before-0.wav --candidate Q3-EEPROM=build/hq4-q3-lpc2-prior/vinni/avr/actual.raw --candidate Rounded=build/q3-rounded-1kb/vinni-eeprom-qualified/avr/actual.raw --build Q3=ATtiny13A/Sound/research/hq4-q3/public-vinni/build.json --build Q3-EEPROM=ATtiny13A/Sound/research/hq4-q3-lpc2-prior/vinni/build.json --build Rounded=ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/build.json --output build/speech-playback-measurements.json
```

Existing build/cache preparation is described in the linked studies. The tool
rejects changed duration, source rate, nonfinite samples, processed audio under
an AVR build label, and a recording that differs from its verified build.
