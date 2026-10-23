# Initial Q3 pulsebook study: explicit joint target not achieved

The requested target is STOI>=.90 **and** spectrogram_loss<=.344975554 on the
unchanged22272-sample Vinni reference at7500Hz. The second threshold is30% below
the current rounded baseline's.4928222194. Actual Flash must fit1024B and all
64EEPROM bytes are reserved for four16-sample signed pulse shapes.

This capture is the first bounded6000-proposal joint table/frame search,
seed23143,68.3seconds. It does **not** meet the target and does not replace
public firmware. The study removes old baseline quality ceilings but keeps
exact arithmetic, duration, byte-size, peak and click guards.

| Final endpoint | STOI | eSTOI | Spectrogram loss | Stream bytes | Rounding |
|---|---:|---:|---:|---:|---|
| Balanced scalar | .840180 | .646196 | .501800 | 615 | Floor |
| Highest STOI | .840448 | .645684 | .504474 | 615 | Floor |
| Lowest spectrum error | .802536 | .593431 | .468277 | 613 | Nearest |

The lowest spectrum error is about5% below the current rounded baseline,
with reduced intelligibility, rather than the requested30% reduction with
STOI>=.90. The best STOI point is only slightly above the floor seed and has
a worse spectrum than the rounded baseline. Neither endpoint substitutes for
meeting the joint target. The new pulse shape space has not been exhausted.

All exported endpoints have zero subtraction/state/negative128/T1 wrap counts,
peak<=115, no steps>=48 and complete duration. These are exact PC guards;
this capture does not claim an assembled/emulated new finalist. The separate
assembler profile's408B floor /410B nearest code provides615/613 stream bytes
plus EOF. EEPROM64B cannot simultaneously contain a speech-stream prefix.

## Seeds and size fitting

Reference: `web-player/audio/originals/vinni.wav`, SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.

Three legacy-table seeds were used, in report order:

1. `research/q3-rounded-eeprom/qualified/model.json`, rounded. Its637B stream
   exceeds the new613B cap. Automatic adjacent coefficient-half reuse reduced
   it to611B; measured resulting STOI.827666 and spectrum.494527 are reported.
2. `research/hq4-q3/public-vinni/model.json`, floor. Its602B stream already fits;
   starting STOI.838396 and spectrum.504357.
3. `research/hq4-q3-lpc2-prior/vinni/model.json`, floor. Its629B stream was
   reduced to615B by real coefficient reuse; STOI.838502, spectrum.504458.

The fit stage never changes timing, pitch, gain or source mode, but it does
change coefficients; it is not asserted to preserve the old audio. All reuse
edits and seed-file hashes are explicit in `vinni/report.json`. Every500
proposals the tool also checked the optional seed directory; no inverse-lattice
learned seeds existed there during this first run. Such seeds belong to a
separate follow-up capture, not this result.

Of6000 proposals,4467 passed all hard checks and673 were accepted by the
exploratory chain. Rejections were1441 invalid layouts/budgets,2 wraps,16 peaks
and74 large-step cases. Table edits and all frame parameter classes were
eligible. The non-dominated frontier retains31 final points, including both
STOI and spectral extremes rather than concealing one in a scalar score.

## Retained artifacts

`vinni/report.json` retains the run configuration, seed fitting, progress,
final metrics, target failure, rejection counts and exact source fingerprints.
`vinni/{balanced,best_stoi,best_spectrum,pareto/NN}/` retain the final model,
actual compressed speech stream,all64 EEPROM table values in the model and
measured quality. Raw EEPROM images, audio and raw PCM remain in ignored
`build/q3-pulsebook/vinni/` and can be regenerated from these parameters alone.
The builder also accepts the retained model JSON directly as its table input.

Source: `../../codec/q3_pulsebook.py`, `../../codec/Q3_PULSEBOOK.md` and
`tools/probe-q3-pulsebook.py`. Five oracle tests and three search tests pass.
The opcode-level independent builder is `tools/build-q3-pulsebook.py`.
