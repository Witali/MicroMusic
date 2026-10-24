# Automatic fixed-time pulsebook seeds

`q3_pulsebook_seed.py` proposes integer `hq4-q3-pulsebook-v1` models for the
separate pulsebook oracle. Returned models contain only normal HQ4 frames,
durations, arithmetic flags and four signed 16-sample EEPROM templates in
[-7, 7]. Decoding needs no original samples, spectra, phase traces or floats.
The helper does not change the decoder or time-warp the source.

```python
model, diagnostics = initialize(reference, frames, durations,
    nearest=True, inverse='byte', local_pitch=False, balance=False,
    stream_budget=613)
model, diagnostics = minimum_phase_initialize(reference, frames, durations,
    nearest=True, selector='cluster', balance=False, blend=.25,
    stream_budget=613)
```

Both methods require a complete finite 7500 Hz reference and already valid,
rate-constrained Q3 fields. Raw integer fields are checked before narrowing
their types. Original sample count, level and DC remain intact. The probe
uses the existing minimum coefficient-half reuse when a 637-byte rounded
incumbent must fit the pulsebook profile's 613-byte stream cap; those edits
are reported. The floor profile's current cap is 615 bytes. These caps come
from separately assembled 410/408-byte cores with all 64 EEPROM bytes occupied
by the book. Candidate full-image qualification still requires the actual
assembler and three-engine verifier; this initializer does not establish it.

The first method learns from the verified float inverse Q3/T1 lattice, or an
exact modular inverse of the integer arithmetic driven by quantized target
bytes. Tests recover known excitation exactly for floor and nearest products,
including noise and changing frames. Packet statistics obey the actual phase
counter: DEC precedes output, so the first voiced sample uses lag1 and lag0
occurs at period-1. Frame changes start at duration0-1. At final sample N-1 the
original oracle advances back to frame0; this sample is also fitted at reset
lag1. No whole period is stretched or moved to align a closure peak.

Four packet clusters initialize discrete alternating mode/gain/template fits.
An optional local pitch fit keeps the incumbent's voiced/unvoiced mask and
tests nearby periods plus sufficiently periodic residual autocorrelation
peaks; it never imposes an LPC2 voice mask. Actual packed bytes constrain every
pitch choice. Unvoiced gains can retain the incumbent or use residual RMS.
This residual least-squares objective is only an initializer: reducing its
error is not a perceptual acceptance criterion.

The second method clusters four normalized log-magnitude residual spectra,
then projects their real cepstra to a causal 16-tap minimum-phase response.
Only the reconstruction keeps the first 16 cepstral taps; clustering itself
uses all log-magnitude bins. It uses no original phase alignment. Selectors
can retain incumbent mode/gain fields or use source-derived spectral cluster
labels with energy compensation. One-to-one matching, energy normalization,
optional exact zero-sum quantization and small legacy-template blends make
explicit bounded alternatives. Neither method changes the target waveform.

The screen tools evaluate actual oracle PCM with the same 70 Hz highpass and
global RMS match used by the existing spectrogram objective. Raw output mean,
RMS, wraps, steps, peak and data bytes are reported separately. A target passes
only if STOI is at least .90 **and** spectrogram loss is at most .344975554.
Higher intelligibility cannot hide a failed spectral target or conversely.

```text
python tools/test-q3-pulsebook-seed.py
python tools/probe-q3-pulsebook-seeds.py --reference web-player/audio/originals/vinni.wav --model floor=build/hq4-q3/public-vinni-t1-spectrogram/model.json --model rounded=build/q3-rounded-1kb/vinni-eeprom-qualified/model.json --output build/q3-pulsebook-seeds/inverse
python tools/probe-q3-minphase-seeds.py --reference web-player/audio/originals/vinni.wav --model floor=build/hq4-q3/public-vinni-t1-spectrogram/model.json --model rounded=build/q3-rounded-1kb/vinni-eeprom-qualified/model.json --output build/q3-pulsebook-seeds/minphase
```

The inverse screen evaluates 64 direct fits plus 48 preservation blends. The
optional minimum-phase follow-up is limited to two source models and 24 seeds.
There is no annealing or corpus sweep. `--retain` keeps the complete score
report plus a few selected model/measurement files; generated audio, packed
data and binaries remain ignored. These Vinni experiments failed the stated
target and are retained as negative evidence, not approved voice replacements.
See [the study](../research/q3-pulsebook-seeds/README.md).
