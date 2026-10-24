# Encoder-only F0 hypothesis experiment

`tiny_pitch_hypotheses.py` and `tools/probe-tiny-pitch-hypotheses.py` add no
decoder source, instruction, state, or format. They generate a bounded set of
source-derived initializations for the existing `period-fixed-v1` Tiny decoder.
The previous `period_wave.py` and `new_tiny_encoder.py` remain unchanged.

Candidates are legacy F0, admissible octave-down, admissible octave-up, and an
automatically estimated persistent soft prior. Octave changes apply only inside
65–850 Hz; inadmissible frames keep their legacy value, and unvoiced frames stay
unvoiced. The existing persistent-run estimator supplies a prior frequency;
only its soft pitch cost is used, not its hard onset or speech masks. There are
no speaker names, source IDs, word boundaries, or manual frequency intervals in
the algorithm.

Each hypothesis independently rebuilds the continuous phase, alignment,
transmitted integer phase trajectory, and 32-point waveform fits. Four- and
eight-word signed-nibble dictionaries use one training start with the same
fixed seed. Gain and white residual initialization use the existing exact
integer functions. Automatic clipping attenuation follows the existing
initializer policy. No broad annealing is performed.

The legacy initialization is an explicit control. Without `--baseline-model`,
the default incumbent is its eight-word version; `--baseline-words 4` changes
that declared control. With `--baseline-model`, the actual known source-associated
model is decoded and protected instead. Its complete padded sample count and
7500-Hz rate must agree with the reference.

Selection requires all six `speech_regression` metrics: no lower STOI/eSTOI and
no higher fine-log, envelope, unsupported-energy, or missing-energy errors.
Flash data cannot exceed the incumbent's actual `pack_tiny` byte count; EEPROM
use stays within 64 bytes. Among passing candidates only a lower structural
spectrogram loss can win. If none wins, the actual incumbent model, Flash data,
EEPROM bytes, and PCM are preserved. The CLI copies the protected model file
byte-for-byte when it is selected, rather than substituting initializer output
with copied incumbent metrics.

Input levels and DC are preserved. The only input transformation is trailing
zero padding to the final 64-sample block. Unsupported sample rates, excessive
lengths, nonfinite audio, or samples outside ±1 are reported explicitly; the
tool does not normalize them. Listening files use a separately disclosed common
filter/RMS/gain process.

Data fit alone is not a total 1-KB claim. The ordinary Tiny builder must measure
code and verify a selected image. Reports identify decoder source changes as
false and leave total-Flash qualification false until a separate build report
exists. Existing protected fallback images retain their earlier qualification.

```powershell
python tools/probe-tiny-pitch-hypotheses.py --reference web-player/audio/originals/chego.wav --baseline-model C:/Work/MicroMusic/.worktree/speech-quality/ATtiny13A/Sound/research/tiny-speech/chego/model.json --output build/tiny-pitch-hypotheses/chego
```

`tools/test-tiny-pitch-hypotheses.py` checks exact equivalence to the frozen
legacy phase/shapes and integer model, admissible octave behavior, protected
good-phrase fallback, and rejection of out-of-range input without gain changes.
