# Persistent frequencies and HQ4 fitting

The retained [analysis.json](analysis.json) comes from canonical, hash-checked
original WAVs and the exact numerical decoder of the frozen **original HQ4**
streams in `codec/release/<clip>/speech.hq`. It does not use the experimental period-wave decoder. No recording
samples, attacks, consonants or sound effects were removed.

The user suggested saving additional frequencies so that they can be rejected
or added when appropriate. This experiment retains them as **offline encoder
guidance**: time spans, median/range of frequency, relative energy, and broad
bands with missing/excess magnitude. There is no new MCU data, filter or
oscillator. The full source remains the target.

## What the originals contain

Automatic analysis at 7.5 kHz finds consecutive narrow spectral ridges lasting
at least 80 ms. The 512-sample Hann window has 14.65 Hz bin spacing and a
68.3 ms duration; actual spectral resolution is poorer than bin spacing and
the start/end estimates can be smeared by about half a window.

| Phrase | Persistent ridges | Examples of strong ridge medians | Largest HQ4 magnitude-error bands |
| --- | ---: | --- | --- |
| Chego | 6 | 380, 523, 1029 Hz | 320–403, 508–640, 1280–1613 Hz |
| Otvechaesh | 5 | 581, 462, 634 Hz | 508–640, 403–508, 1280–1613 Hz |
| Vinni | 23 | 123–124, 779–798, 1563–1636 Hz | 1613–2032, 127–160, 1280–1613, 101–127 Hz |

These are time-local measurements, not a set of stationary frequencies that
should run throughout a phrase. For example, Vinni's ridge near 798 Hz extends
from approximately 1.382 to 1.664 s, with frequency estimates moving from
766 to 821 Hz. A 1563 Hz ridge occurs around 0.196–0.350 s, whereas the
1636 Hz ridge occurs around 1.527–1.647 s. A fixed added tone would neither
follow those trajectories nor reproduce their attack and decay.

The Vinni baseline has substantial magnitude deficits around 101–160 Hz and
both missing and excess energy around 1.3–2.0 kHz. Fitting only the pitch
cannot address all these errors. The report ranks deficits and excesses
separately. Their values are squared positive differences between **STFT
magnitudes**, normalized by reference spectral energy; they are not the energy
of a phase-correct waveform residual and must not be interpreted as such.

Narrow ridges, harmonic structure and formants are different observations.
A voice harmonic can sit under a broad formant envelope. A ringing effect
can also be narrow and persistent. Proximity to an estimated integer multiple
of F0 is recorded only as a `harmonic_context_candidate`; it does not prove
the origin of the component. At higher harmonic numbers, accidental matches
are increasingly plausible. There is no `noise` label or automatic notch.

## Encoder objective

`codec/speech_spectrum.py` exposes:

```python
from speech_spectrum import PersistentSpectrumObjective
objective = PersistentSpectrumObjective(original_signed_float, 7500)
metrics = objective.evaluate(decoded_signed_float)
```

The decoder output must preserve the original sample count. Both inputs pass
through the same 70 Hz second-order Butterworth highpass; candidate output is
globally RMS-matched. No alignment, frequency warping, trimming or phase
fitting is performed.

- `band_envelope_loss`: weighted absolute difference between temporal
  one-third-octave envelopes, normalized to unit RMS within each band. This
  follows syllables and attacks independently of static frequency gains.
- `band_shape_loss`: weighted natural-log difference between per-frame
  unit-L2 band vectors, with a relative magnitude floor of 0.01. This retains
  spectral-envelope/timbre information that the first term normalizes away.
- `band_loss`: equal-weight average of those two complementary terms.
- `persistent_spectral_error`: full-bin natural-log magnitude error with
  reference-derived weights between 1 and 3 around persistent ridges.
  Nonpersistent bins retain weight 1, so short consonants still contribute.
- `unweighted_spectral_error`: the same single-window comparison without
  ridge emphasis. It differs from the existing multi-window spectral metric.

Band and temporal weights come only from the reference. Weak bands receive
0.25 rather than zero weight; frame weights range from 0.25 to 1. All
parameters are automatic and shared by all phrases. The metrics are useful
optimization objectives, **not standardized listening-quality scores**. A
candidate must also satisfy independent full-record STOI/eSTOI and baseline
spectral constraints, followed by level-matched listening. Adding these scores
does not itself demonstrate better speech.

| Exact original HQ4 baseline | Envelope loss | Band shape loss | Combined band loss |
| --- | ---: | ---: | ---: |
| Chego | 0.530361 | 1.276948 | 0.903655 |
| Otvechaesh | 0.468816 | 1.226005 | 0.847411 |
| Vinni | 0.393252 | 1.063867 | 0.728559 |

Use the band objective first when changing existing HQ4 pitch, gain,
excitation, reflection coefficients and frame durations. A notch or extra
oscillator should be a separate optional experiment only after that search
shows a residual that the existing decoder cannot represent, and only if
quantized extra parameters improve intelligibility/shape within the actual
Flash, SRAM and cycle budgets. There is currently no evidence for blindly
removing or overlaying the listed frequencies.

## Reproduction and tests

From the repository root, with the existing codec Python dependencies:

```powershell
python tools/analyze-speech-spectrum.py --output build/speech-spectrum/analysis.json
python tools/test-speech-spectrum.py
```

The default references are the tracked canonical WAVs in
`web-player/audio/originals`. An alternative decoded WAV can be compared with
`--clip vinni --candidate-wav <path>`. The report retains normalized source
hashes, original and candidate hashes, numerical PCM hashes and runtime
versions. It does not run or replace the independent AVR emulator checks.

Seven tests cover exact identity, gain/polarity independence, a persistent
extra tone, short and disjoint ringing attacks, harmonic-context ambiguity,
changed syllable timing, and invalid data/duration. On this machine, a Vinni
objective setup took about 53 ms and cached candidate evaluation about 3 ms
(300 evaluations, single OpenBLAS thread); timings are informational.
