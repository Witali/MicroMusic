# Unchanged HQ4 baseline on the RU/EN test corpus

`tools/benchmark-speech-corpus.py` is a reusable corpus runner for the existing
406-byte signed-byte HQ4 numerical decoder. It uses the generic automatic
initializer with the same parameters for every recording, 617-byte stream
budget and zero annealing proposals by default. It does not contain character,
language or speaker-dependent fitting rules.

## Actual baseline run

The deterministic prepared manifest has SHA-256
`4b6c7b7a039cba2794465e4b4c7412c5b7e49b60894b4132ae87615116cab982`.
All 20 short center excerpts and four full recordings completed. The full
selection was fixed before inspecting quality: `ru_pushkin_a`,
`ru_slutskaya_a`, `en_letter_a`, `en_portrait_a`. It includes one male and one
female voice per language, with two tuning and two evaluation recordings.

| Subset | Complete / selected | STOI range | Estimated Flash range | Raw five-dB bound passes |
| --- | ---: | ---: | ---: | ---: |
| Short, 2.048 seconds | 20 / 20 | 0.374–0.739 | 656–1018 bytes | 0 / 20 |
| Full, approximately 8 seconds | 4 / 4 | 0.438–0.636 | 908–980 bytes | 0 / 4 |

These are baseline measurements, not accepted speech quality or an improvement
claim. All models passed independent stream unpack/repack and full numerical
PCM equality checks. Flash uses actual serialized stream size plus the frozen
406-byte core, an EOF marker and even-byte alignment. **No example was
assembled, AVR-verified or hardware-tested by this runner.** Those estimates
do not establish cycle timing, SRAM use or a deployable firmware fit.

Raw prepared input level, DC, resampling overshoot and every sample are retained.
Raw numerical output is saved without normalization. Means, RMS, peaks,
endpoint counts, large sample steps and input/output RMS ratios accompany each
recording. Spectrogram/tracking metrics with one global RMS match are clearly
separate from raw-level partial metrics and strict bounds. Both raw and
level-matched five-dB audits fail on all 24 examples.

The quiet cases reveal a concrete baseline limitation: the existing initializer
chooses gain relative to each input's own RMS. RU quiet input RMS 0.0031207
becomes raw output RMS 0.0647693 (20.75 times); EN quiet input RMS 0.00079444
becomes 0.0536859 (67.58 times). Their output DC is approximately four signed
PWM units despite zero endpoint clips. A globally level-matched quality score
alone would conceal this amplitude error. Future general gain/DC corrections
must therefore retain the raw-level checks as well as intelligibility and
spectrum checks on each protected recording.

## Usage and comparison

```
python tools/benchmark-speech-corpus.py \
  --manifest build/speech-corpus/manifest.json \
  --references-root build/speech-corpus \
  --output build/speech-corpus-benchmark/short \
  --subset short \
  --retain ATtiny13A/Sound/research/test-corpus/hq4-baseline-short
```

`--subset full --ids ru_pushkin_a ru_slutskaya_a en_letter_a en_portrait_a`
reproduces the full selection. IDs may be exact prepared IDs or source-clip
IDs within the selected subset. Unknown IDs fail instead of silently reducing
coverage. `--proposals N` optionally enables a bounded existing exact-decoder
search; the baseline uses zero. Reference paths remain relative to the declared
root and their prepared hashes/sample rates/counts are checked before use.

Every selected recording produces a report entry, including infeasible and
failed encodes. Descriptive aggregates by language, split and condition include
status counts and never decide regression acceptance. `--baseline-report`
compares a future run per recording and metric using the regression guard. It
also requires unchanged recording IDs, reference hashes, sample counts/rates,
manifest hash, subset and input-level policy. Changing a reference cannot pass
merely because the measured scores improved. No averaging can hide harm to a
protected recording.

Retained `hq4-baseline-short/` and `hq4-baseline-full/` contain only JSON models
and reports with normalized-LF source hashes, runtime versions and relative
references. Original/derived audio, raw PCM and stream binaries stay in ignored
build output. The finite test corpus provides regression evidence, not a
guarantee for arbitrary unseen voices.

`python tools/test-speech-corpus-benchmark.py` passes six tests covering subset
selection, unknown IDs, exact packing, EOF/alignment estimates, unchanged quiet
and DC statistics, complete failure accounting, path confinement, per-recording
regressions and changed-reference rejection.
