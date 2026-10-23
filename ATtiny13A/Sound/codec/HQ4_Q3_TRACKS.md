# Optional harmonic-track fitting of an existing Q3 model

`tools/probe-hq4-q3-tracks.py` starts from an explicitly identified, frozen
`hq4-q3-v1` model. It does not replace the previous Q3 fitter, modify a retained
input, or alter the AVR decoder. `--harmonic-tracks 10` compares up to the ten
strongest automatically detected local partials at each unchanged time, using
`harmonic_tracks.HarmonicTrackObjective`. The count can be reduced to 1–9.
Tracks are not assumed to be exact multiples of a chosen fundamental.

Every proposal uses the exact Q3 byte decoder. The searchable fields remain
all eight reflection coefficients, pitch period and voiced/unvoiced choice,
gain, the four excitation-shape choices, frame boundaries, and split/merge
operations. Coefficient-half reuse can free stream bytes. No frequency, word,
or speaker-specific interval is supplied manually.

The primary objective is original/output difference:

```
difference_loss = 0.5 * (spectrogram_loss + harmonic_track_loss)
```

STOI and eSTOI are hard floors measured on the complete frozen input model;
they are not reward terms. Exported elites also preserve all four previous
spectrogram components: fine log error, mel-envelope error, unsupported energy,
and missing energy. Their harmonic matching loss, missing reference energy,
extra candidate energy, and continuity-break rate cannot worsen, while weighted
matched-reference coverage cannot decrease. This prevents improving matched-only
frequency/level averages by discarding difficult reference partials.

Simulated-annealing working states may violate those guards to cross local
barriers. The report counts these separately from feasible candidates and
accepted elites. Only a fully feasible elite is exported, and the report says
whether the packed stream actually changed. There is no claim of success when
the best feasible result is the unchanged baseline.

All sample, byte, intermediate-wrap, peak, and adjacent-step constraints remain
in force. The default stream budget is 603 bytes for Q3-T1 or 615 for plain Q3;
use `--stream-budget 430` for the bell composite's speech allocation. `--build`
qualifies a standalone profile through the existing exact AVR builder; a bell
composite still requires its separate full-image verification.

The output includes all baseline/final components, absolute frequency and level
errors from the track objective, its complete matching/tolerance configuration,
input/source hashes, accepted-elite history, decoded PCM, and RMS-matched audio
in original → previous Q3 → track-fitted order. Generated media stays under
ignored build output. Retain only qualified source models and research reports.

Example:

```powershell
python tools/probe-hq4-q3-tracks.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --output build/hq4-q3-tracks/public-vinni --proposals 4000 --harmonic-tracks 10
```

`tools/test-hq4-q3-tracks.py` verifies that a better aggregate cannot bypass an
individual intelligibility, spectral, missing-track, extra-track, coverage, or
continuity guard.
