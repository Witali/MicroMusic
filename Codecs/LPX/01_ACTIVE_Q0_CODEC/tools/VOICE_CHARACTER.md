# Host-only voice-character diagnostics

`voice_character.py` adds an analysis tool alongside the unchanged PCM/PWM
SSE/STOI metrics. It changes no encoder default, stream syntax, MCU arithmetic,
playback gain, sample rate or waveform. It does not identify a speaker or voice
gender. Periodicity and coarse spectral shape are numerical evidence, not a
validated perceptual-quality or true-F0 score.

The independent implementation uses the difference function, cumulative-mean
normalization, first qualifying trough and local parabolic interpolation from
the YIN approach. The basis is [de Cheveigne and Kawahara, JASA 2002,
DOI 10.1121/1.1458024](https://doi.org/10.1121/1.1458024)
([paper](https://www.ee.columbia.edu/~dpwe/papers/deChevK02-yin.pdf)), with the sequence also
described in [the official librosa YIN documentation](https://librosa.org/doc/main/api/generated/librosa.yin.html).
The selected period is interpolated on the raw difference as described in
paper step 5, avoiding the normalized curve's period bias at fractional search
boundaries. Confidence still uses the normalized trough depth.
No external implementation is copied. This deliberately bounded estimator omits
YIN's additional temporal refinement and pYIN's probabilistic model. Unlike a
tracker that always returns its best minimum, it leaves F0 unknown when no local
trough passes the threshold. Threshold crossings are periodicity observations,
not ground-truth voiced/unvoiced labels or calibrated probabilities.

## Interface

```python
settings = PitchSettings()  # immutable
source = track_pitch(reference_pcm16, settings)
report = compare_voice(reference_pcm16, decoded_pcm16, settings,
                       reference_track=source)
```

The default is 8 kHz, 640-sample frames, a 160-sample hop, 50–800 Hz and a
CMNDF trough threshold of 0.15. The range is independent of the codec's lag
range, allowing out-of-codec-range source behavior to remain visible. Temporary
frame scaling occurs only inside numerical analysis; no returned audio is
normalized. A source frame below 0.5 PCM16 RMS after removing its DC level is
below this diagnostic's resolution floor. These defaults were chosen before
inspecting the user-targeted recording; no corpus split selected them.

`PitchTrack` owns read-only `frame_start`, `sample_center`, `period`, `hz`,
`confidence`, `rms`, `voiced` and `status` arrays. Settings and the sample count
are frozen. Unknown periods/hz are NaN internally, while JSON reports use null.
The hidden source binding rejects reuse with another equal-length recording;
it is not emitted. Complete input lengths must match. No alignment, resampling,
edge padding or gain fitting takes place. The trailing part shorter than one
hop and boundary periods can lack a complete analysis window; source/output
level descriptors still use every original sample. Short inputs are reported
as unassessed rather than padded into fabricated pitch observations.

`fixed_periodicity_error(frame, source_period)` compares a fractional-period
shift using the same support on both sides. It is available even when decoded
pitch tracking fails. It returns 0 for a matching period, roughly 1 for an
uncorrelated signal and exactly 1 for a vanished/constant signal. Thus dropping
the output to zero cannot evade a frozen-source comparison. Reference and
decoded values are both reported because finite quantization and interpolation
can give a nonzero reference residual.

`spectral_shape_error(reference_frame, decoded_frame)` compares 24 equal-width
relative-power bands from mean-removed Hann periodograms. Relative powers use
a -80 dB floor. Gain is factored out only in this shape descriptor; original
RMS/peak/nonzero samples remain separate. A vanished spectrum pays the explicit
log floor instead of becoming a missing best-case score. This is a coarse
shape comparison, not a formant estimator. It can also change with pitch.

`compare_voice` keeps reference-supported frame positions fixed, counts missing
decoded periods as failures, reports paired cents and half/double-pitch counts,
and retains fixed-period and spectral-shape errors. Its 100-cent tolerance is
an explicit project diagnostic setting, not a universal audibility threshold.
No source periods means *unassessed*, not successful preservation. Pass native
PCM16 and `standard_metrics.pwm_pcm16(decoded)` in separate calls; 8-bit output
can erase a tone which remains representable in PCM16.

## Checks

Seven focused test groups cover known analytic periods, PCM16 amplitudes from
1 to 4096, fractional search boundaries, octave changes, altered harmonic shape,
analysis gain invariance with unchanged reported levels, white-noise/zero output,
PWM disappearance, source silence, short inputs, frozen state and wrong-source
track reuse. Tests make no corpus-wide quality claim. The tool cannot recover
information already absent from a quantized source.
