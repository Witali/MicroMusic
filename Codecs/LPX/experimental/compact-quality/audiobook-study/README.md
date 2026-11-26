# Continuous 20-second P3 audiobook study

This study extends the existing protected P3 fine-grid encoder phase from
64,000 to 160,000 samples. Each example is one continuous 20-second, 8-kHz
V9 Long stream. The completed P3 file is the immutable baseline and actual
byte ceiling B0. Candidate generation and all production selection guards
remain the preceding implementation; no decoder or wire-format code changed.

The extension selected three development improvements and **zero of eight
held-out improvements**. The held-out files and decoded output remain exactly
the baseline, while the extra encoder search still consumes time. This study
does not justify promoting the Long extension as a default quality improvement.
Its frozen source and evidence are retained as an experiment; the guards are
not relaxed to admit rejected proposals.
The preceding short-study policy at `654a95c7` remains the verified reference
for further work. These held-out outcomes are now seen data; a tuned successor
needs another prospectively frozen evaluation cohort.

The source-only cohort contains twenty fixed excerpts from the user's local
collection, split into twelve development and eight held-out examples before
encoding. The source interval is 120..140 seconds, mono PCM16 at 8 kHz, without
level fitting, normalization, silence trimming, alignment or repeated padding.
Original-file identity and normalized title/chapter aliases define groups;
narrator and underlying-book independence are not established. All titles,
source paths, media/stream fingerprints, model payloads and audio stay ignored.

One `QualityTarget::Pwm` operation per example protects and measures both PCM
and PWM. A separate PCM-only search is outside this study. The efficient
baseline-plus-helper composition is independently equivalent to the complete
automatic operation; it performs one baseline encode and one optional search,
with at most two isolated native worker processes.

## Results

Each table entry compares the completed current P3 baseline with the
automatically selected output, including unchanged fallbacks. STOI means use
all examples in their own split, with separate PCM and PWM paths.

| Group | Cases | Selected changes | Complete bytes | Mean PCM STOI | Mean PWM STOI |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 12 | 3 | 87,316 → 87,210 | .748109 → .760533 | .740600 → .750366 |
| Held-out | 8 | 0 | 58,108 → 58,108 | .732770 → .732770 | .725845 → .725845 |

Development's summed PCM error energy falls 7.5693%, and PWM error energy
falls 7.5437%. The 106-byte saving is 0.1214%; quality improvement is the
larger observed effect. All twelve complete cases passed. Nine selected
outputs remain exactly the baseline: three raw proposals were unchanged,
four were rejected by spectrum safety, one by the octave guard and one by
the remaining quality selector. The four safety rollbacks remain recorded
as optional errors, not omitted or confused with whole-encode failures.

All eight held-out cases also passed complete execution and decoding. Six raw
proposals were rejected by spectrum safety; two were unchanged. The six
optional safety errors remain in the report. Raw totals were 57,806 bytes,
mean PCM STOI .772493 and PWM STOI .758559. These include six rejected proposals
and two unchanged returns, not delivered savings or quality gains. No held-out
outcome changed the policy or caused another encoding attempt. Development
and held-out means stay separate.

The [final policy declaration](POLICY_FREEZE.md) retains this initial arm
without retuning before held-out evaluation. The first admitted development
example is 7,236 → 7,195 bytes, PCM STOI .735744 → .776484 and PWM STOI
.725044 → .757995. Its local listening export is posthoc development evidence.

Development band replay covers only the three changed selected outputs:
24 supported band/case/path entries, all with lower magnitude error, no
aggregate error-floor failures and no added relative octave observations.
Capped retention is lower in nine PCM and eight PWM entries; all three
changed examples fail that separate strict research diagnostic. Retention
is an energy proxy and is not interchangeable with reconstruction error.

The retained [development rows](results-development.json),
[read-only validation](validation-development.json) and
[posthoc bands](posthoc-bands-development.json) contain anonymous numerical
results and software provenance. The [recovered pilot](results-pilot-recovery.json)
and [pilot validation](validation-pilot-recovery.json) are included once in
development. The [denied dispatch](results-pilot.json) has no native outcome.
The [held-out rows](results-heldout.json), [held-out validation](validation-heldout.json)
and [zero-change band report](posthoc-bands-heldout.json) retain the independent
evaluation. All twenty examples were STOI-eligible on both paths, with no
missing variant scores.

Native component CPU times per 20-second example were:

| Group | Mean baseline CPU seconds | Mean optional-helper CPU seconds |
| --- | ---: | ---: |
| Development | 54.55 | 27.38 |
| Held-out | 65.62 | 35.84 |

These are single measurements of the tested composition, not a controlled
automatic-API speed ratio or decoder/AVR timing. No quality/size benefit was
admitted in the held-out group to offset its additional encoder work.

## Evidence and interpretation

The [registered protocol](PROTOCOL.md) and [development/held-out phases](PHASES.md)
were committed before audiobook outcomes. No criterion, threshold, byte budget,
source membership or candidate arm was retuned from these outcomes. The
optional raw proposal and the automatically selected output are reported
separately. Rejected proposals do not count as admitted quality improvements.

STOI membership is frozen from each baseline and path. A missing eligible
score makes the corresponding mean unavailable; it never silently reduces
the denominator. File-byte totals include every registered case. Global
1-kHz band error and capped retention are separate posthoc diagnostics, not
new selection guards or listening-test results.

The [independent Long gate](LONG_TESTS.md) passed six groups covering actual
17-byte headers, high sample/payload words, complete native PCM/PWM and EOF,
same-B0 selection and rollback, macro-off predecessor identity, unchanged
short-input results, carried-state streaming and full-operation composition.
The frozen runner's four tests and synthetic Long adapter smoke also passed.
Saved LPX, full host models and PCM are replayed without encoding or search;
Python independently recounts the Long bits and PCM/PWM error energies.

Both completed phase validators passed twenty cases and 180 artifact files.
Independent phase audits also checked all 180 hashes and freshly replayed
sixty saved baseline/raw/selected outputs, each through complete native PCM,
actual PWM, model, EOF, metric and selector checks. The held-out audit confirms
that the exact root policy declaration predates all eight attempts and that
development evidence, software and binary stayed unchanged. Detailed audit
receipts remain ignored because they bind private media and artifact hashes.

An initial WSL dispatch was denied before the native encoder started. Its
failed attempt is preserved separately. Independently verified recovery used
identical scientific inputs, source bytes, options and binary. See
[execution notes](RUN_NOTES.md). This was not a repeated speech search.

## Scope

STOI and signal diagnostics are objective measurements, not a claim of a
blind listening preference. Local listening exports preserve the prepared
source and exact decoded levels; PWM previews are duty averages of the
verified static transfer, not physical-board recordings.

Recorded baseline/helper timings are native host component measurements,
including helper validation and evaluation construction. They are not a
separately timed full automatic API call or an AVR cycle comparison. This
study does not establish new ATtiny88/ATmega328P memory, interrupt timing or
Long-input support. Actual WASM execution and peak memory are unmeasured.
Changed spectral-repeat or detail activity can change existing decoder work,
so unchanged decoder source does not establish equal AVR cycles.

[Storage guidance](STORAGE_GUIDANCE.md) records about 128 KiB for embedded
local storage and GiB-scale PC/external-flash media as nonbinding design
orientations. They add no new rejection threshold and do not imply that
existing APIs support GiB streaming.
