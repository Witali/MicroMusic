# Low-rate LPX quality search

This study compares new encoder proposals with the complete current V3 search
at `ba02e453`. The V9 syntax, decoder, source level and complete file caps stay
fixed. [PROTOCOL.md](PROTOCOL.md) was written before the new holdout outputs.
The equations and independent evaluators are reused from
[`v9-quality-all-2026-11-23`](../v9-quality-all-2026-11-23/).

The strict 3/8-kbit/s settings here are legacy whole-file budget policies.
This study does not validate the separate in-progress P3/P4/P6/P8 accuracy-tier
UI, and strict 8 kbit/s is not the new P8 tier.

## Source freeze

The new primary has 12 unseen whole utterances, totaling 69.07725 seconds:
three Russian and three English FLEURS sources at 16 kHz, and six distinct
VCTK speakers at 48 kHz. Durations range from 4.02192 to 7.98 seconds.
Original bindings, available hashes and VCTK speakers exclude the entire
previous 24-source primary. Checks also cover retained old-27/public provenance;
those older records and FLEURS lack stable speaker IDs, limiting speaker-level
overlap claims.

Each source has a direct native-to-8-kHz strict-3-kbit/s target and a direct
native-to-16-kHz P4 target: 24 primary jobs. All source media, identities,
provenance, detailed receipts and decoded outputs remain in ignored `build/`.
All 12 direct-16-kHz references have supported source energy in both 6–7-kHz
and 7–8-kHz bands under the existing greater-than-1e-4-of-total-power rule.
This source-only check uses the frozen 512/256 symmetric-Hann transform.
Primary encoding began only after algorithm freeze `403de620`. Before its
first encode, the private run contract bound the unchanged source manifest,
both actual binaries and their source-file hashes, build receipts and octave
addendum. No source replacement or quality refitting follows that freeze.

The old 27-case corpus is now known development/regression material: 108 jobs
across P4/P6/3-kbit/s/8-kbit/s at 8 kHz. Former held-out labels are retained only
as private provenance. Exact prior V3 references are reused after verifying all
target, stream, PCM and PWM bindings; their original binary provenance and
historical timings are preserved.

## Public prototype-v2 pilot

The three already public tuning phrases cover eight settings each. This is
tuning evidence with narrowband source material, including its resampled
12/16-kHz targets. It cannot establish new wideband generalization.

All 24 outputs pass the unchanged independent v2 admission rule; 11 decoded
outputs change. Complete file totals are 26,764 bytes before and after. One
8-kbit/s file grows by one byte and one P4/16-kHz file shrinks by one, within
the same original caps.

| Profile | Rate | Changed / 3 | Mean objective score |
| --- | ---: | ---: | ---: |
| 3 kbit/s | 8 kHz | 2 | 0.995135 |
| 8 kbit/s | 8 kHz | 3 | 0.983070 |
| P4 | 8 kHz | 2 | 0.998558 |
| P6 | 8 kHz | 2 | 0.992934 |
| P4 | 12 kHz | 0 | 1.000000 |
| P6 | 12 kHz | 0 | 1.000000 |
| P4 | 16 kHz | 1 | 0.999797 |
| P6 | 16 kHz | 1 | 0.998256 |

Each reference score is 1. The score averages frozen-incumbent-relative losses
with spectral and temporal weights 2, and voice, noise, waveform, STOI loss,
period and shape weights 1 where defined, across PCM and PWM. These scores are
objective comparisons, not perceived-quality percentages.

At 3 kbit/s, the mean balanced spectral errors fall by 0.726% PCM / 0.705% PWM,
balanced temporal errors by 0.595% / 0.656%, and mean STOI rises by
0.000811 / 0.000859. Waveform SSE rises by 0.197% / 0.261%; peak errors rise
from 27,575 to 28,239 PCM and 27,607 to 28,119 PWM units. PWM rails rise from
3 to 4, with no PCM clipping. All 24 cases retain spectral/time/STOI floors,
but individual voice, noise, period, shape, waveform, peak and noisy-frame
diagnostics include regressions. Independent native-rate pitch observations
lose no 100-cent matches, gain one per output path, and show no newly missing,
half-pitch or double-pitch observations. This is not validated true F0.

The prototype API total is 164.881 seconds; the reused V3 total is a historical
127.326 seconds. The two totals are not an isolated speed benchmark. These
tuning results alone cannot establish a result on unseen sources.

## Public-v3 pilot before the octave guard

The final proposal keeps the LPC-run edits and adds at most two all/top-two
bundles under the same score and safety rules. A bounded development ablation
removed raw regeneration: five tested pairs were byte-identical while taking
roughly twice the API time. No new-primary output informed that choice.

The final 24-case tuning pass still changes 11 outputs and admits all 24.
Two outputs differ from the prototype: mean P6/8-kHz score becomes 0.990428
and strict-3-kbit/s score becomes 0.993717; the other six table rows stay equal.
Complete bytes are 26,764 → 26,765, within the unchanged per-file caps.

Final strict-3-kbit/s balanced spectral errors fall by 0.871% PCM / 0.846% PWM,
balanced temporal errors by 0.865% / 0.914%, and mean STOI rises by
0.001518 / 0.001511. PCM waveform SSE falls by 0.011%; PWM SSE rises by 0.062%.
Peak and PWM-rail regressions remain as listed above. Across the full pilot,
waveform SSE worsens in three cases per path; peak error worsens in five PCM
and three PWM cases. Voice, noise, period, shape and noisy-frame diagnostics
also contain regressions, retained in [the complete anonymous report](public-final-v3.json).

Native-rate pitch observations still lose no 100-cent matches and gain one per
path, but now add one near-half-pitch observation per path in a public P6/8-kHz
case. This is a distinct tradeoff; the fixed production pitch view and
independent YIN observations are not interchangeable. The final API total,
240.053 seconds, was collected under concurrent work and cannot establish a
speed ratio against the historical or earlier prototype timings.

The public pitch finding led to the prospective
[per-window octave floor](PITCH_GUARD.md), specified before any new-primary
encoding. The public-v3 report above is preserved as pre-guard evidence;
guarded results require a separately frozen candidate and receipt directory.

## Guarded selected public result

Freeze `403de620` admits all 24 public cases under both the unchanged v2 gate
and the independent per-window octave check. Ten outputs change from V3.
Strict-3-kbit/s mean score is 0.996027, with one of three outputs changed;
P6/8-kHz mean score is 0.991406. The other six profile/rate means stay equal
to the pre-guard result. One formerly improved 3-kbit/s file conservatively
returns to its exact V3 incumbent. Full bytes remain 26,764 → 26,765.

The independent audit observes no new half/double labels, no lost matches,
one gained match per path and no new missing observations. At 3 kbit/s,
balanced spectral errors fall by 0.637% PCM / 0.642% PWM, temporal errors by
0.663% / 0.673%, and mean STOI rises by 0.001512 / 0.001448. Waveform SSE
rises by 0.056% / 0.074%; the peak regressions remain, but PWM rails stay
3 → 3 and PCM clips stay zero.

Across all 24 cases, waveform SSE worsens in four cases per path and peak
error worsens in four PCM / two PWM cases. Individual voice, noise, period,
shape and noisy-frame regressions remain visible in the
[complete guarded report](public-guarded-selected.json). The candidate API
total is 151.337 seconds, with the same historical/concurrency caveats.
This public tuning result is separate from the new primary.

## New primary result

Both encoders completed all 24 fixed jobs. Five outputs change: four of twelve
strict-3-kbit/s files and one of twelve P4/16-kHz files. All 24 pass the
unchanged independent v2 admission and the additional native-rate per-window
octave check. Exact complete bytes stay 81,112 → 81,112, under the same caps.

| Profile | Cases | Changed | Mean score before | Mean score after |
| --- | ---: | ---: | ---: | ---: |
| Strict 3 kbit/s, 8 kHz | 12 | 4 | 1 | 0.998926523 |
| P4, 16 kHz | 12 | 1 | 1 | 0.999893398 |

These are small objective gains, not demonstrated audible improvements. The
strict-3-kbit/s mean balanced spectral error falls 0.103% PCM / 0.091% PWM,
temporal error 0.090% / 0.082%, and pooled waveform SSE 0.101% / 0.082%.
Mean STOI rises approximately 0.000080 / 0.000090. P4/16-kHz gains are smaller:
spectral error falls 0.0085% / 0.0050%, temporal error 0.0088% / 0.0045%, and
waveform SSE 0.0315% / 0.0411%.

At 3 kbit/s, the pooled 3–4-kHz magnitude error falls 0.724% PCM / 0.780% PWM.
On source-classified noisy/unvoiced frames, that band's magnitude error falls
1.054% / 1.101%, envelope MSE 1.744% / 1.861%, and onset MSE 0.087% / 0.214%.
Individual noisy-frame and onset spikes still worsen in some cases despite
these pooled improvements.

P4/16-kHz improvement is not uniform across upper bands: 7–8-kHz magnitude
error rises 0.00136% PCM / 0.00505% PWM. Pooled 6–8-kHz error rises 0.000712%
PCM and falls 0.001543% PWM; some envelope/onset means also worsen slightly.
Its worst source-noisy spikes above 6 kHz do not rise. Every source supports
both upper 1-kHz bands; their small regressions are not discarded as silence.

No primary case has worse waveform SSE, voice loss, shape loss, STOI or the
guarded broad spectral/time metrics. Noise and period losses worsen in two
cases per path. Per-case peak error worsens in two PCM / one PWM cases even
though the cohort's largest peak error stays equal. PCM clips and PWM rails
stay zero. Native-rate observations have no lost/gained 100-cent matches and
no newly missing, half-pitch or double-pitch labels. These remain heuristic
observations, not validated true F0.

The [complete primary report](primary-guarded-selected.json) includes all
physical bands, source-supported/quiet bands, noisy subsets, envelope/onset
means and worst-frame spikes. Baseline API totals 546.105 seconds and candidate
643.428 seconds were measured under different bounded concurrency; they are
not an isolated speed ratio. The quality search adds no decoder arithmetic or
wire fields. P4/P6 names and the V9 format stay fixed.

## Known regression result

The established 27-case corpus is development/regression material, not a new
independent holdout. All 108 jobs at 8 kHz pass the semantic v2 and additional
octave checks; 44 outputs change, eleven per setting. Complete bytes rise
223,814 → 223,819, within the same original caps.

| Setting | Mean score before | Mean score after | Byte delta |
| --- | ---: | ---: | ---: |
| Strict 3 kbit/s | 0.962962963 | 0.957704379 | +4 |
| Strict 8 kbit/s | 0.962962963 | 0.961738588 | +1 |
| P4 | 0.962962963 | 0.961914120 | −1 |
| P6 | 0.962962963 | 0.961899723 | +1 |

The baseline mean is exactly 26/27 because the silent case has zero score;
these are raw means of per-file incumbent-relative losses, not perceived-quality
percentages. All 28 non-speech controls pass both the semantic score without
speech STOI and the separate production-term mathematical audit. The latter
has 48 assessed STOI paths and includes that term only to check production
parity. The scores differ by up to 0.005389; neither interpretation establishes
music intelligibility. See [the control audit](known-control-score-definitions.json).

Per-case waveform SSE worsens in 30 PCM / 31 PWM cases and peak error in
11 / 6. Voice, noise, period, shape and noisy/onset tradeoffs remain in the
[complete regression report](known-regression-guarded-selected.json). Existing
clip/rail totals do not increase. Native observations lose no matches, gain
three PCM / four PWM matches, and add no missing, half- or double-pitch labels.

[VALIDATION.md](VALIDATION.md) records final selected-backend parity and exact
current decoding of all 312 baseline/selected streams, covering 11,052,658
PCM/PWM samples. Full metric detail stays in the anonymous JSON reports.

## Harness commands

Use the project's Python evaluation environment, with NumPy, SciPy and pystoi.
The driver is native C++; Python supplies only preparation and evaluation.
All paths below are relative to the task worktree.

```powershell
python Codecs/LPX/research/lowrate-quality-next-2026-11-23/study.py freeze-baseline --output build/lowrate-quality-next/baseline-ba02
python Codecs/LPX/research/lowrate-quality-next-2026-11-23/study.py prepare --help
python Codecs/LPX/research/lowrate-quality-next-2026-11-23/study.py prepare-public --help
python Codecs/LPX/research/lowrate-quality-next-2026-11-23/prepare_regression.py --help
```

After the owner freezes the candidate, `build-candidate` snapshots its source
and builds the same native seam. `run --phase baseline` requires the archived
baseline binary. `run --phase candidate --baseline <receipt-directory>` uses
the baseline's exact complete caps. The wrapper rejects changed protocol,
preparer, evaluator or target bindings. Shards partition fixed jobs by index;
coordinate at most three numerical workers across the team.

The shared `pitch_tradeoffs.py` and `final_report.py` consume complete baseline
and candidate receipt directories. `report.py` invokes them unchanged and sets
this study's labels and historical-timing caveat. They export anonymous
aggregates and keep source paths, hashes, media, frame arrays and time indices
private. Inspect v2 admission fields: the older waveform-floor progress flag
is diagnostic only. For guarded output, pass its private `--guard-contract`:
the wrapper checks the frozen manifest/addendum/binary binding and exports
the additional octave-floor result without changing any original score.
