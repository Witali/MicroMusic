# Original and actual AVR waveform shapes

The final phrase includes its bell and preserves all 19328 samples at 7500 Hz.
The Q3 candidate is the qualified 1022-byte Flash / 64-byte EEPROM build in
`build/hq4-q3-tracks/bell-hybrid`. The input reader checks its complete phrase
plus two phrase lengths of midpoint silence before removing that silence.
The original WAV, actual AVR RAW and analysis-source hashes are in the report.

`tools/compare-speech-waveforms.py` applies the same 70 Hz highpass and one
global RMS match. It selects three separated voice windows automatically from
reference lowpass autocorrelation, starting at voice sample 6528. No vowel or
frequency is selected by hand. Both same-clock and best local phase-shift
plots are retained. A separate fitted local gain measures remaining shape
error; it does not modify listening audio or the plotted curves.

| Original time, s | Best phase-shift correlation | Shape NRMSE after phase and local gain |
| --- | ---: | ---: |
| 1.0304–1.0517 | 0.869 | 0.496 |
| 1.3395–1.3571 | 0.421 | 0.907 |
| 2.0168–2.0451 | 0.478 | 0.878 |

The first selected interval becomes fairly similar after a phase shift. In
the other two, the output has sharp sparse peaks and weaker inter-peak detail
than the original. Their remaining differences are not explained by a fixed
time or phase offset. These selected windows diagnose the model limitation;
they do not establish a perceptual rating or a whole-phrase quality score.
The phase shifts and local gains must not be used to claim actual synthesis
accuracy. Waveform correlation alone is not a naturalness objective.

The unfiltered actual output also has a mean of 0.02174 full scale, about
2.78 PWM levels above midpoint; the original mean is -0.000015. The plots
remove this DC with the common analysis highpass. This does not correct the
firmware's raw PWM offset. A future output-stage change must be checked
separately for bias, asymmetric clipping, code size and timer margin.

Reproduction from the development checkout:

```
python tools/compare-speech-waveforms.py \
  --reference build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav \
  --candidate build/hq4-q3-tracks/bell-hybrid/actual.raw \
  --label "Q3 AVR output" --start-sample 6528 \
  --output build/speech-waveforms/tail
```

Only figures and the JSON report are retained here. Original and generated
audio remain in ignored build directories.
