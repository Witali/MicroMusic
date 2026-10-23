# Automatic fitting against the original spectrogram

The user rejected Q4/T1 as still squeaky and requested closer spectrograms.
Shared-scale figures show that global spectral tilt does not recover the
original moving formant ridges. Extra energy remains between ridges, while
some source ridges are too weak. No individual frequency was selected by hand.

`codec/spectrogram_objective.py` derives its complete targets from the original:
256/1024-sample Hann spectra, exact-bin log distance, 32 broad mel envelopes,
and separate missing/excess magnitude-energy errors with a one-bin frequency
tolerance. Both signals receive identical 70 Hz highpass and one global RMS
match. The complete time axis is preserved. This is a diagnostic objective,
not a standardized naturalness score.

## Fixed-decoder control

`tools/refine-hq4-spectrogram.py` searches pitch, excitation mode, amplitude,
all eight reflection coefficients, sharing groups and frame boundaries through
the exact signed-byte decoder. The exported elite must preserve both frozen
STOI/eSTOI floors, both original spectral ceilings and every new component
ceiling. Lower scalar loss cannot hide increased missing/unsupported energy
or a worse broad envelope. Exploratory states can cross these boundaries;
only the feasible elite is exported. Internal wraps and large steps are rejected.

The bounded public-Vinni control is reproducible with 6000 proposals, seed 23170:
STOI .859602 → .859631, eSTOI .690986 → .691165, structural loss .629696 → .625560.
All four components improve, but the size of the improvement is small. The
unchanged 406-byte decoder plus 617-byte stream fits 1024 Flash bytes and is
verified for one full phrase plus twice its duration of silence in three engines.
It is not presented as a solution to the audible complaint.

```sh
python tools/refine-hq4-spectrogram.py \
  --reference web-player/audio/originals/vinni.wav \
  --stream ATtiny13A/Sound/codec/release/vinni/speech.hq \
  --output build/spectrogram-match/vinni-refit --proposals 6000 --seed 23170 \
  --build --avr-bin <avr-bin> --node <node>
```

## Separate wider-coefficient candidate

[Q3 models and qualification](../hq4-q3/README.md) preserve their separate
arithmetic profile. Against the rejected Q4/T1 preview, Vinni's structural
loss falls .565548 → .504357 and unsupported energy .260780 → .200681; STOI
falls .845375 → .838396 and eSTOI .667041 → .644611. This remains an audition
tradeoff. The actual image is 1024 Flash bytes, no EEPROM.

The final phrase's voice improves every component and both intelligibility
proxies at the same 430-byte stream cap: structural loss .617131 → .538359,
envelope .680350 → .548592, unsupported energy .270521 → .186957,
STOI .825079 → .836672, eSTOI .519951 → .550572. Its complete bell-plus-voice
[image](../hq4-q3/bell-hybrid/README.md) is 1022 Flash + 64 EEPROM bytes.
The bell's amplitudes are also fitted automatically to the source-relative
voice level. No subjective naturalness acceptance is claimed.

`independent-check.json` is a separate reconstruction/HEX/EEPROM/report check:
model synthesis equals actual AVR phrase PCM, and the remaining two phrase
lengths are midpoint silence. Its scores are recomputed from actual PCM.
`vinni.png` and `tail-voice.png` use Original / Previous-T1 / Q3-auto on shared
color scales. The voice figure excludes the first 6528 bell samples only for
diagnosis; the executable and full listening comparison retain them.

```sh
python tools/compare-speech-spectrograms.py \
  --reference web-player/audio/originals/vinni.wav \
  --candidate Previous-T1=build/new-speech/natural-timbre/public-vinni/avr/actual.raw \
  --candidate Q3-auto=build/hq4-q3/public-vinni-t1-spectrogram/avr/actual.raw \
  --output build/spectrogram-match/vinni-final --listen
```

The plotting tool accepts a complete unsigned-byte phrase, or the standard
verified raw recording consisting of that phrase followed by twice its length
of midpoint silence. Other raw lengths or non-silent extended tails are rejected.
It exports the original followed by each named candidate at matched RMS and
one shared peak scale. Audio, optimizer checkpoints and assembled firmware
remain in ignored `build/`; compressed models and research are retained here.

The next required control is tracking up to ten strongest partials through
time and matching their frequencies, levels and persistence to the original.
That requirement supplements the full spectrogram; it must not discard speech
outside the strongest ten components or replace intelligibility checks.
