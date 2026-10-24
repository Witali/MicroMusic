# Preserving a tonal strike alongside speech

`tools/probe-hq4-bell.py` refines an existing full HQ4 model without changing its
format or the 406-byte decoder. It is a diagnostic experiment, not an automatic
semantic bell classifier. A group of strong persistent spectral ridges beginning
within 128 ms of the earliest high-frequency onset supplies alternative periods,
including periods 2..11 missing from the initial pitch analyzer's candidates.
All eight integer harmonics of each detected component also supply alternatives.

```sh
python tools/probe-hq4-bell.py --reference build/input/reference.wav \
  --model build/hq4/model.json --output build/hq4-tonal --proposals 5000 --seed 23121
```

Only parameter frames overlapping the automatically selected tonal group change.
No input samples are removed or resampled. Every accepted change must improve
the selected ridges' RMS-matched log-magnitude error, preserve the original full
recording's STOI and deterministic eSTOI, fit 617 stream bytes, remain under the
original whole-band spectral-loss ceiling plus three percent, and pass the same
peak and discontinuity checks. Coefficient edits may update a whole existing
sharing run so the scarce parameter bytes need not grow. The report retains
both baseline and candidate metrics, selected ridges, changed frame indices,
source hashes, exact PCM/stream hashes and full proposal history.

The reported frequency ridges can belong to speech, music or an effect. The
eight-bit lattice's single periodic excitation produces harmonics of one integer
sample period. It cannot in general reproduce several independent inharmonic
bell modes at once; changing pulse shape or filtering does not remove this
limitation. A lower diagnostic error is therefore not a claim that the original
bell has been recovered. Compare original, baseline and candidate audio, then
independently assemble and verify the actual HEX before selecting a release.

`tools/test-hq4-tonal-probe.py` checks event selection on an unrelated synthetic
multimode strike followed by a separate tone and on a low-frequency voice-like
signal, so the selected region is not tied to one film excerpt.
