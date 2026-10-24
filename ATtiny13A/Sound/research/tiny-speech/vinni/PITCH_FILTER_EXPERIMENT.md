# Vinni with persistent-voice analysis

This is the requested complete processing of “Сова! Открывай! Медведь пришёл!”
with the new `voice-priority` analysis. It is a PC experiment. The existing HQ4
firmware remains the public player choice because this candidate has lower STOI.

The encoder estimates a persistent voice prior of 128.96 Hz from an automatic
102.4 ms continuous interval. It excludes rejected attacks from voice-pitch
analysis and wavebook training, while preserving all 22,272 source samples.
Rejected attacks use the existing unvoiced noise path. No manual speech or
sound-effect timestamps were supplied.

The same seed, eight wavebook starts and 80 ms minimum persistent interval are
recorded in `pitch-filter-quality.json`. The subsequent 2,000 frame proposals
can change gains and noise colors, but cannot reclassify rejected frames as
voiced. No additional search followed this run.

| Full-record measure | Voice-priority initialization | After 2,000 proposals | Existing HQ4 |
| --- | ---: | ---: | ---: |
| STOI | 0.51135 | 0.59856 | 0.85960 |
| Log spectral error | 0.71197 | 0.67809 | 0.81288 |

The spectrum became closer than HQ4 under this measure, but intelligibility did
not improve. The diagnostic on the same concatenated automatic voice blocks is
also lower than HQ4: 0.62886 versus 0.76478. Concatenation changes STOI context;
these values are additional diagnostics, not full-record scores. The separate
unfiltered initializer with zero refinement proposals is not an equal-search
control for this 2,000-proposal result.

## Listening files

Generated audio stays in ignored `build/tiny-speech/vinni/voice-priority-filter/vinni/`:

- `original.wav`: original reference, with the common listening filter and level.
- `hq4.wav`: existing HQ4 before the experiment, under the same listening setup.
- `filtered.wav`: the new processed result; identical to `period-16x32.wav`.
- `comparison.wav`: original → HQ4 → original → processed, separated by 300 ms.

All individual WAVs contain 22,272 mono PCM16 samples at 7,500 Hz. File hashes,
sample counts, runtime versions and encoder source hashes are in the retained
report. The model hash is
`aadc030da53dcd907cde68f156cef4c618afd01ea0df7c020e78c81efe72fa3a`.
Packing and unpacking its 962-byte parameter payload preserves decoded PCM
exactly. This payload size includes no AVR decoder, and no AVR fit or hardware
validation is claimed for this experiment.

## Reproduction

Use the canonical original identified by SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`
under an external or ignored `<references>/vinni/original.wav` directory:

```text
python tools/probe-period-wave.py --clip vinni --voice-priority --references <references> --output build/tiny-speech/vinni/voice-priority-filter --starts 8 --proposals 2000 --plot
```

The minimum persistent interval defaults to 80 ms; the current CLI also accepts
`--pitch-min-run-ms 80` explicitly. On Windows, set `PYTHONIOENCODING=utf-8` for
the Russian result title. Copy `period-16x32.wav` to `filtered.wav` for the stable
listening alias. The retained model is `pitch-filter-model.json`; the output
directory also contains the native parameter payload and F0/mask diagnostics.
