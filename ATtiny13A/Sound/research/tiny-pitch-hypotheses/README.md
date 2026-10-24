# First encoder-only step: multiple source-derived pitch hypotheses

This bounded experiment uses the existing Tiny integer decoder and four/eight
32-point waveform dictionaries. Each candidate independently fits legacy F0,
admissible half/double octaves, or a source-derived persistent soft prior. All
dictionary fits use one start and seed 23230. There is no manual speaker rule,
phoneme boundary, time selection, input gain change, or broad annealing.
The existing initializer and decoder sources remain unchanged.

Selection protects six per-recording metrics, not an average: STOI/eSTOI cannot
fall, while fine-log, envelope, unsupported-energy and missing-energy errors
cannot rise. The actual packed Flash-data budget is the incumbent's byte count;
EEPROM use remains within 64 bytes. Only a passing candidate with lower
structural loss can replace the incumbent. Otherwise its actual model, Flash,
EEPROM and PCM are preserved.

## Twelve explicit recordings

Chego and Otvechaesh protect their actual published Tiny models, each with
260 Flash-data bytes. Vinni and the final tail voice use explicit legacy
eight-word initializer controls; these controls are weaker than the existing
public HQ4/Q3 voices and do not replace them.

The new corpus trial uses one natural `_a` center-2.048-second window from each
of four Russian and four English sources, following
`../../test-corpus/manifest.json` and its attribution. No additional crop or
level/DC normalization is performed. The source-disjoint tuning/evaluation
labels are retained. A centered window may cut words and is not a complete
phrase claim.

| Recording | Baseline STOI | Selected STOI | Result |
|---|---:|---:|---|
| Chego, protected public Tiny | 0.910667 | 0.910667 | Exact incumbent |
| Otvechaesh, protected public Tiny | 0.840897 | 0.840897 | Exact incumbent |
| Vinni, generic initializer | 0.550834 | 0.550834 | Exact incumbent |
| Tail voice, generic initializer | 0.606377 | 0.606377 | Exact incumbent |
| ru_pushkin_a, tuning | 0.437083 | 0.437083 | Exact incumbent |
| ru_square_a, tuning | 0.560113 | 0.560113 | Exact incumbent |
| ru_slutskaya_a, evaluation | 0.514731 | 0.514731 | Exact incumbent |
| ru_russia_a, evaluation | 0.673249 | 0.673249 | Exact incumbent |
| en_sense_a, tuning | 0.421067 | 0.425601 | Persistent soft prior |
| en_portrait_a, tuning | 0.555645 | 0.555645 | Exact incumbent |
| en_letter_a, evaluation | 0.603882 | 0.603882 | Exact incumbent |
| en_normcore_a, evaluation | 0.625359 | 0.625359 | Exact incumbent |

Eleven of twelve keep the actual incumbent. The single improvement is on a
tuning source; no evaluation source improves. This demonstrates a useful finite
case and protected fallbacks, not generalization or natural-sounding speech.
The absolute quality of the successful generic initializer is still low.

## One qualified improvement, with no decoder growth

For `en_sense_a-center2048`, the automatic prior is 79.15 Hz and changes two F0
analysis frames. The resulting eight-word dictionary is refitted jointly.

| Measurement | Legacy eight-word control | Selected soft-prior candidate |
|---|---:|---:|
| STOI | 0.421067 | 0.425601 |
| eSTOI | 0.125337 | 0.142614 |
| Fine log error | 1.198520 | 1.185239 |
| Envelope error | 0.540174 | 0.521928 |
| Unsupported energy | 0.399166 | 0.375071 |
| Missing energy | 0.156316 | 0.141602 |
| Structural spectrogram loss | 0.840273 | 0.823956 |
| Packed Flash-data bytes | 287 | 267 |
| Actual AVR decoder bytes | 714 | 714 |
| Actual total Flash bytes | 1002 | 982 |
| EEPROM used bytes | 64 | 64 |
| Minimum preparation slack, cycles | 216 | 296 |

Both images are actually assembled by the unchanged Tiny builder and checked
against all three emulator engines: 46080 identical PCM samples each, consisting
of the complete 15360-sample phrase window and twice as much midpoint silence.
There are no lost overflows or missed samples. Compiler, source, 9.6-MHz CPU and
7.5-kHz sample rate are unchanged. The 20-byte reduction is data, with zero code
growth. One linker alignment byte is included in each total.

This actual total-Flash qualification applies to that pair. The other generic
initializer controls are data-budget experiments; they are not claimed to fit
1 KB until built. No hardware or human-listening qualification is asserted.

## Retained evidence and reproduction

`summary.json` links every per-recording report. Reports retain all eight
hypothesis/dictionary trials, every failed metric gate, exact input/source
fingerprints and data/EEPROM/PCM hashes. Generic selected models are retained;
the successful pair also retains its baseline model and both actual AVR build
reports. Unchanged protected public models are linked instead of duplicated.
Original audio is not copied into these research directories.

```powershell
python tools/probe-tiny-pitch-hypotheses.py --reference build/speech-corpus/clips/en_sense_a-center2048/reference.wav --output build/tiny-pitch-hypotheses/reproduce
python tools/build-tiny-speech.py --model ATtiny13A/Sound/research/tiny-pitch-hypotheses/en_sense_a-center2048/model.json --output build/tiny-pitch-hypotheses/reproduce-avr --play-once --avr-bin <avr-bin> --node <node>
python tools/test-tiny-pitch-hypotheses.py
```

Four tests cover exact legacy phase/shapes/packing equivalence, admissible octave
changes, actual good-phrase fallback, and rejection of out-of-range input without
gain changes. Further work should improve held-out sources while preserving
these concrete incumbent models and all individual guards.
