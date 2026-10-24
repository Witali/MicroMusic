# Strict five-decibel audit of every selected original partial

The requested bound is stronger than a weighted mean or a 95th percentile:
**every** selected original partial must be matched at the same time and its
absolute level error must be <=5 dB. A missing original partial is a violation,
not a zero-error frequency/level observation. Level dB uses 20log10(amplitude
ratio), equivalently 10log10(power ratio).

`codec/partial_bounds.py` implements `check_partial_bounds(details, ...)` on
the unchanged track objective's detailed assignment. It counts the union of
missing, excessive-level and optional excessive-frequency errors. It reports
both the fraction of selected peaks violating and the fraction of selected
original partial power carried by those violations. Frequency limits are
optional; if both cents and Hz bounds are requested, both must hold.

This audit covers selected original partials. Extra output peaks are reported
separately and are not implicitly bounded by this level-only check. Full
spectrogram, extra-energy, coverage and codec constraints remain necessary.
When nothing matches, `max_matched_level_error_db` is null, not zero.

## Current qualified Q3 examples

The audit uses actual AVR PCM from the already qualified builds, preserving
the original full phrase timing. The Vinni actual file contains a complete
22272-sample phrase followed by twice its length of midpoint silence; the
reader validates and removes only that trailing silence. The selected build
is `build/hq4-q3/public-vinni-t1-spectrogram/avr/actual.raw`.

The final voice is exactly samples `[6528:19328]` from
`build/hq4-q3-tracks/bell-hybrid/actual.raw`. Before selecting them, the complete
57984-byte output is checked for the expected 19328-sample phrase and 38656
samples of midpoint silence. The 12800-byte selected voice matches its
independently generated `tail-voice/expected.raw` exactly. Full/source/slice
hashes and indices are retained in `tail-voice-source.json`.

| Actual voice | Selected original peaks | Missing | Matched levels >5 dB | Union violating | Violating original partial power | Worst matched level error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vinni Q3 | 1605 | 830 | 288 | 1118 | 71.54% | 20.30 dB |
| Final phrase Q3 tracks | 1010 | 602 | 114 | 716 | 50.99% | 18.67 dB |

**Both fail the requested strict bound.** The worst matched errors do not
include the missing peaks; those independently fail the presence requirement.
No claim that the current firmware reaches five-decibel accuracy is made.

The reports identify automatic contiguous violation windows of roughly
250 ms. Vinni's largest violating-power window is 1.536–1.792 s; the final
voice's is 0–0.256 s. These times are local to the original voice recording,
without time alignment or manual selection. The selected partial definition
and finite STFT resolution remain those documented in
`codec/HARMONIC_TRACKS.md`.

## Reproduction

```
python tools/check-partial-bounds.py \
  --reference path/to/original.wav \
  --candidate "Candidate=path/to/actual-avr.raw" \
  --max-level-db 5 \
  --output build/strict-bounds.json
```

Add `--max-frequency-cents` or `--max-frequency-hz` for explicit frequency
constraints. The reference and WAV/RAW candidate must retain the same sample
rate and phrase length. Metadata, source hashes, candidate hashes, tracker
configuration, worst intervals and all scalar track metrics are written to
JSON. No original or generated audio is retained here.

`python tools/test-partial-bounds.py` verifies exact-threshold acceptance,
single-peak rejection, missing/all-missing handling, power weighting, optional
frequency caps, union counts and one-to-one assignment. Four tests pass.
