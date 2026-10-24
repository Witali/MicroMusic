# Ten strongest components through time

The same original-derived `HarmonicTrackObjective` is used by automatic
coefficient search, tolerance-constrained byte reduction and these figures.
`vinni.png` and `tail.png` compare the rejected Q4/T1 playback to the wider Q3
profile after bounded trajectory fitting. Every frame retains at most ten
strongest local peaks. IDs follow their frequency motion, not amplitude rank.
Grey is the original; colored curves are matched output; red dots mark missing
original components and orange crosses extra output components.

`metrics.json` stores configuration, input hashes and summarized measurements.
Full trajectories, one-to-one assignments and the exact plotting inputs remain
in ignored `build/spectrogram-match/{vinni,tail}-tracks/harmonic-tracks.json`.
Recreate them using `tools/compare-harmonic-tracks.py` and the retained models'
actual AVR recordings. The plotting and numerical source hashes are recorded.

The figures cover the whole recording, including the bell in the second one.
The loud bell improves the whole-recording matching fraction; it must not hide
the weaker speech-only match. `independent-tail.json` recomputes both whole and
voice-only quality from the qualified actual 1022-byte Flash/64-byte EEPROM
image. The entire phrase, EEPROM, model synthesis and midpoint silence agree.

The full Vinni Q3 model matches 82.7% of the selected original partial power,
against 77.9% for Q4/T1. This still leaves substantial missing/extra power.
Its bounded 4000-proposal trajectory search found no additional feasible win.
The new voice-only search improves mean frequency error 39.16 → 38.34 cents
and mean level error 5.473 → 5.381 dB, a small gain. Its p95 level error rises
slightly, 13.8803 → 13.8827 dB; a lower mean does not establish a p95 bound.
Qualified fitting data are in `research/hq4-q3-tracks/`.

## Tolerance and real compression

`tools/compress-hq4-q3-tracks.py` minimizes actual `pack_stream` bytes by sharing
coefficient runs, legal frame merges and bounded coefficient repair. It never
drops time samples. Larger frequency/amplitude caps enlarge the feasible set;
a sweep starts each looser level from the previous result, so its data size
cannot grow. Noise/partial disappearance cannot falsely improve the result:
missing/extra power, match coverage and continuity remain frozen-input guards.

Absolute-original bounds and explicitly named `--relative-to-baseline`
additional-error bounds are separate modes. Frequency can use cents or Hz;
amplitude uses dB after the one global RMS match. `--error-statistic p95`
means original-power-weighted matched-partial percentiles, not every point.
Use `--error-statistic max` to bound every matched point; missing partials
remain subject to their separate guard. Mean bounds are also available.
`--minimum-stoi` or `--maximum-stoi-drop` adds independent intelligibility
control: good harmonic caps alone do not guarantee good speech.

Example absolute-original p95 sweep on the 430-byte voice model:

```sh
python tools/compress-hq4-q3-tracks.py \
  --reference build/new-speech/bell-hybrid/voice-reference.wav \
  --model ATtiny13A/Sound/research/hq4-q3/tail-voice/model.json \
  --output build/q3-track-rate/tail-absolute \
  --sweep 75:15,100:16,150:18 --frequency-unit cents \
  --error-statistic p95 --max-evaluations 300 --layout bell
```

The bounded sweep produced 329 / 237 / 219 data bytes, with STOI
.7966 / .7132 / .6727. These are compression tradeoffs, not naturalness upgrades.
Code, bell descriptors, end marker, alignment and EEPROM are counted separately
from compressed voice bytes. Only reports from the independent AVR builder
qualify an executable image; a computed fit is not qualification.

The existing models fail absolute 50-cent/3-dB p95 limits. Such cases retain
their measured errors and an explicit infeasible status instead of silently
relabeling baseline distortion as acceptable.
