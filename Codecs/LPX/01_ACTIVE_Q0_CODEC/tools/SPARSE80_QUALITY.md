# Fixed-budget sparse80 quality searches

These opt-in host tools propose different values in the existing v8/15 or
v9/15 stream. They add no decoder instructions, synthesis state or file fields.
All recording parameters remain in the sound file. P4/P6 streams are rejected
by these wrappers; their encoder defaults are unchanged.

## Filter refinement

`refine_sparse80.refine(reference, blob, decoder)` searches the existing
deemphasis/brightness words, preserving every payload byte and the exact file
length. It combines coordinate descent with a paired grid: increasing both
filter coefficients can reveal a useful candidate missed from brightness zero.
The default bounds are 1024 inexpensive error evaluations and 64 full metric
evaluations. The shared ordinary-v5 helper accepts optional `extra_pairs`;
omitting them retains its previous search and other-profile behavior.

The reference must be the complete original-level mono PCM16 signal at 8 kHz.
No output gain fitting, resampling, quiet-sample deletion or reference alignment
is performed. Use an independent ordinary-v5/P6 C receiver; the sparse adapter
expands innovations for that oracle without changing the candidate's byte cost.

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/refine_sparse80.py \
  reference-8k.wav baseline.lpx build/refined
```

The CLI needs NumPy/Numba/SciPy, SoundFile and the existing batch native compiler
setup. `--non-speech` disables speech-only STOI assessment. Outputs are
`audio.lpx`, the exact PWM-domain `decoded.wav`, and a private numerical report.

## Pulse decisions

`enhance_sparse80.enhance(reference, blob, decoder)` also explores beam pulse
decisions with widths 2/4 and three proposal penalties: plain error, output
clipping, and internal/output clipping. The last penalty affects search costs
only; it never changes the integer synthesis recurrence. The kernel adapts the
project's earlier bounded beam experiment and accounts for only declared tail
samples. It keeps spectra, pitch/scale metadata and the seven-bit innovation
alphabet fixed. Nonzero input brightness skips the zero-brightness beam stage.

It compares whole-beam proposals, transferred filter pairs, up to four local
320-sample pulse patches, and a filter search on the best admitted pulse
proposal. Duplicate streams skip metric work. The input remains a protected
rollback, and serialized candidates larger than it are rejected.

```python
from batch_decoder import BatchSession
from enhance_sparse80 import enhance

with BatchSession('batch', speech=True, speech_compact=True,
                  compact_only=True) as reference_decoder:
    selected, pcm16, report = enhance(original_pcm16, stream, reference_decoder)
```

## Admission and limits

Both searches retain original-level PCM16 and actual fixed-transfer PWM8 error
energy, available whole-signal STOI, source-period tolerance counts, collapsed
active-frame counts, fixed-period error, and PCM/PWM clipping floors. A lower
joint voice/noise proxy ranks admitted candidates. Individual spectral-shape
diagnostics can trade off and stay visible; numerical admission does not prove
cleaner sound, transparency, subjective preference or preservation of all voice
characteristics. Missing STOI is unassessed, not a substituted score.

Every selected output must match the independent native C PCM16 and PWM bytes.
No decoder arithmetic changes are hidden in the encoder. Low-bit-rate sparse
excitation can sound rough even with zero internal saturation; filter tuning
alone need not remove that effect. Extra host search is not a real-time decoder
cost, but each selected stream still needs full-player active-IRQ admission
before an AVR real-time claim.

For a corpus study, freeze source and settings, preserve all samples and source
levels, and protect the whole recording after reset segmentation. Concatenate
baseline/candidate outputs, compare whole-record metrics, and roll back the
entire record if those floors fail. Count votes per original recording and
report speech/music/cohorts separately. Compare actual PWM waveforms: a PCM-only
or microscopic score change is not evidence that the 8-bit hardware sounds
better. Neither the public tuning examples nor these APIs establish a majority
improvement on an unmeasured corpus.

## Experimental pulse neighbors and upper-band guards

`refine_sparse80_pulses.refine` is a separate, **experimental, not admitted**
local-neighbor stage. It preserves spectra, pitch/scale metadata, filters and
the seven-bit alphabet, checks the complete native C output, and rejects
PCM-only proposals whose PWM bytes do not change. Its fixed upper-band error
and burst bounds are enabled by default. The CLI's
`--allow-frequency-regression` is an explicit research control.

A preceding Chego prototype was rejected on listening: rasp moved upward and
became more noticeable despite better aggregate metrics. The fixed-band checks
catch that exact case, including partial terminal windows. They do not prove
that an admitted candidate sounds cleaner. This stage is not automatically
applied by the encoder, the combined search above, or any WebUI firmware build.
[Measurements and hypotheses](../../../../docs/avr-asm-cookbook/lpx-lowrate-quality.md)
explain the distinction and the unchanged C/ASM playback contract.
