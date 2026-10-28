# Reference-frozen voice search objective

`speech_voice_objective.VoiceObjective` is an opt-in host search criterion. It
does not change v5, decoder arithmetic, output gain or the old automatic quality
gate. It is an original bounded search heuristic, not a standardized perceptual
score. Lower scores must not be reported as percentages of audible quality.

The fixed starting weights are waveform 0.25, spectral shape 1 and periodicity
2. They were chosen to make the synthetic octave, missing-output and envelope
regressions distinct before a new corpus search, not fitted to the user example.

Each 80-ms window starts every 20 ms. Original-level squared waveform error is
divided by reference energy with a one-PCM16-count RMS floor; this gives quiet
regions a contribution instead of letting loud regions dominate. It never
rescales the decoded audio. Spectral features are square roots of 32 band power
fractions from a centered Hann periodogram; they describe shape independently
of level, while waveform error still penalizes an incorrect level. Terminal
partial windows remain in waveform/shape calculations.

Reliable source periods come from the separate [voice diagnostic](VOICE_CHARACTER.md):

```python
track = track_pitch(reference)
objective = VoiceObjective(reference, track.period)
loss = objective(decoded_pcm16)
```

The objective freezes same-support fractional-delay difference profiles at
0.5, 1, 1.5 and 2 times each source period. The octave alternatives matter:
matching one full period alone cannot distinguish a doubled frequency. A zero
or constant decoded window has difference 1, not perfect periodicity. Decoded
pitch tracking never determines which reference windows count. Unknown source
pitch disables that window's periodicity term explicitly; waveform and shape
still count. Empty pitch coverage does not establish pitch preservation.

The batched Numba arithmetic is kept separate from the independent diagnostic
implementation. Synthetic alternating samples give the exact profile
`[2, 0, 2, 0]`; tests also compare correct quiet tones against both octaves,
missing output and changed harmonic envelopes. Gain invariance is a property
of analysis above input quantization, not a promise to recover a source that
has quantized to silence.

`score_range` can screen a bounded candidate only when it includes full source
windows and their preceding context. A partial interval with no complete
analysis window falls back to waveform error and reports zero voice windows.
Local screening is not a complete-waveform admission. Final candidates require
full-length native/model PCM/PWM equality, real serialized caps, separate old
SSE/STOI checks and explicit listening. Unchanged decoder code does not by
itself admit different data under real-time IRQ loads.
