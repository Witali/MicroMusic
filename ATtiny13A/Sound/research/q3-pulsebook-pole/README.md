# Extended-pole pulsebook study: target not achieved

This separately tagged profile assigns packed coefficient nibble0 to -15/16;
other coefficients retain `(nibble-8)/8`. It does not reinterpret ordinary
Q3 data or replace public firmware. The frozen decoder and original joint
search sources are unchanged by this retention commit.

The absolute target was STOI>=.90 **and** spectrogram_loss<=.344975554 for the
complete22272-sample Vinni reference at7500Hz. The6000-proposal study, seed23311,
did **not** meet that target.

| Final endpoint | STOI | eSTOI | Spectrum loss | Stream B | Rounding |
|---|---:|---:|---:|---:|---|
| Balanced / highest STOI | .842286 | .650890 | .497696 | 591 | Floor |
| Lowest spectrum error | .799542 | .588943 | .469244 | 588 | Nearest |

The old extended-pole cores measured430B floor /434B nearest, with593/589B
actual speech capacity plus EOF in1024B Flash. All64 EEPROM bytes contain the
pulsebook. These data constraints, not the later compact-core capacities,
were used by this study. Final parameters pass the exact PC byte-wrap, peak,
sample-step and duration guards; this capture does not claim a new final
assembled firmware or hardware test. Later COREOPT/DATAOPT work is retained
separately in `../q3-core-data-cycles/`.

The raw mean of the balanced output is+.075964 versus an original mean near
zero. No hidden output gain or DC correction was applied. A small increase in
STOI or a separate spectrum endpoint is not a satisfactory joint quality win.

## Seed procedure and provenance

The wrapper `tools/probe-q3-pulsebook-pole.py` first fits source streams to the
actual593/589B budgets by coefficient-half reuse. It screens masks
`0,1,3,15,255`, promoting selected -7/8 coefficient values to -15/16, and
gain scales.65/.85/1 for nonzero masks. The zero-mask control uses unchanged
gain. Three source models produce39 recorded screen trials, including rejected
ones. Their unchanged source hashes identify:

- `research/q3-pulsebook/vinni/balanced/model.json`;
- `research/q3-pulsebook/vinni/best_spectrum/model.json`;
- `research/q3-rounded-eeprom/qualified/model.json`.

Four selected screen seeds start the stochastic search. Directory polling
subsequently adds94 inverse-lattice seed models, yielding98 recorded inputs.
`vinni/seed-inputs.json` retains compact, complete parameter snapshots for all98
inputs: actual HQ4 stream bytes encoded as base64,64 signed table entries,
rounding, tilt, source-model hashes and relative provenance. No original audio
or reference waveform is embedded. `seed-screen.json` retains all39 first-stage
trials; report seed hashes are not replaced by reconstructed-model hashes.

The run did not log the exact proposal number at which each asynchronously
arriving directory seed was added. Therefore the exact stochastic trajectory
cannot be promised from the final input set alone. Final audio and quality are
reproducible directly from the retained final models, stream and decoder; all
three exported endpoint labels were independently rescored during retention.
The compact seed snapshots also prevent dependence on temporary build models.

4372 of6000 proposals passed hard guards and604 were accepted; rejections were
1538 layouts/budgets,2 wraps,16 peaks and72 sample-step cases. Total recorded
runtime was107.5seconds. The source hashes in the original report still match
the retained wrapper and frozen numerical/search implementations.

## Reproduction and artifacts

Reference `web-player/audio/originals/vinni.wav` has SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.

For a fresh study with the same screen procedure:

```powershell
python tools/probe-q3-pulsebook-pole.py `
  --reference web-player/audio/originals/vinni.wav `
  --model ATtiny13A/Sound/research/q3-pulsebook/vinni/balanced/model.json `
  --model ATtiny13A/Sound/research/q3-pulsebook/vinni/best_spectrum/model.json `
  --model ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json `
  --extra-seed-directory build/q3-pulsebook-seeds `
  --output build/q3-pulsebook-pole/repeat --proposals 6000 --seed 23311
```

This command creates a new capture; seed arrival timing can change its path.
`vinni/report.json`, `seed-screen.json`, `seed-inputs.json` and
`retention-verification.json` retain measured evidence. The three final labels
retain `model.json`, actual `speech.hq` and `quality.json`; balanced and best_stoi
are identical endpoints in this capture. The stored model provides all64
EEPROM values. WAV, raw PCM, compiled images and temporary files stay in build.
