# Completed frozen V3 quality study

All **96 genuine-wideband and 108 narrowband jobs** completed and passed
independent admission. V3 changed 12 and 11 outputs respectively; other outputs
retained the incumbent. Gains are small and uneven. Listening has not established
an audible improvement; objective scores are not perceived-quality percentages.

The primary cohort has 24 complete 4–8-second utterances: 12 official FLEURS at
16 kHz and 12 official VCTK at 48 kHz, with source content above 6 kHz after
direct native-to-16-kHz preparation. Eight tuning cases precede 16 held-out cases.
The separate established corpus has 27 full four-second references: 10 tuning
speech, 10 held-out speech and seven negative controls. These are case counts,
not independent-speaker counts. No allocation, weight or threshold changed after
held-out outputs were viewed.

Both encoders receive identical prepared PCM, source level, complete duration
and byte budgets: no fitted gain, delay, trimming or output alignment. Analysis
covers every band through the actual 4/6/8-kHz Nyquist limits at 8/12/16 kHz.
Upsampled 8-kHz sources are not used to claim retained source highs above 4 kHz.

## Score definition and per-profile delta

For each PCM/PWM path, average incumbent-relative losses: balanced magnitude
and temporal magnitude-change errors at weight two each; voice, noise and
full-rate waveform SSE at weight one each; plus 1-STOI, source-period error
and coarse spectral-shape error at weight one when the incumbent is finite.
A zero incumbent loss is an exact zero floor. The complete frame, normalization
and safety definitions are in the [frozen addendum](PROTOCOL_WIDEBAND.md).

The delta is an **absolute difference of mean score units**, not a percentage.
Compare before/after within a row, not raw values across profiles/cohorts.
One silence control has exact zero loss, so narrowband baseline means are
26/27 rather than one; that case stays in the denominator.

| Setting | Jobs | Changed | Mean before | Mean after | Absolute delta | Complete bytes before → after |
|---|---:|---:|---:|---:|---:|---:|
| P4, 8 kHz | 27 | 4 | 0.962963 | 0.961527 | −0.001436 | 43,261 → 43,261 |
| P6, 8 kHz | 27 | 2 | 0.962963 | 0.961377 | −0.001586 | 65,117 → 65,117 |
| 3 kbit/s budget, 8 kHz | 27 | 5 | 0.962963 | 0.957148 | −0.005815 | 39,946 → 39,942 |
| 8 kbit/s budget, 8 kHz | 27 | 0 | 0.962963 | 0.962963 | 0 | 75,494 → 75,494 |
| P4, 12 kHz | 24 | 4 | 1.000000 | 0.997981 | −0.002019 | 81,722 → 81,722 |
| P6, 12 kHz | 24 | 3 | 1.000000 | 0.999200 | −0.000800 | 122,946 → 122,946 |
| P4, 16 kHz | 24 | 4 | 1.000000 | 0.997679 | −0.002321 | 108,023 → 108,023 |
| P6, 16 kHz | 24 | 1 | 1.000000 | 0.999831 | −0.000169 | 162,975 → 162,975 |

Wideband totals **475,666 → 475,666 bytes**; narrowband **223,818 → 223,814**.
Combined: **699,484 → 699,480**, no growth cases and one four-byte reduction.
Formal 8-kbit/s corpus outputs remain unchanged; its positive example is in
the separate public tuning pilot. Budget labels describe ceilings, not a
promise that every file fills its available budget.

## All-metric tradeoffs

All native-rate STOI memberships, complete sample counts/rates and declared
caps are retained. PCM clipping never increases. Balanced magnitude/time floors
pass on both paths. Individual components and peaks can nevertheless worsen.

| Worsened diagnostic, cases per output path | Wideband PCM / PWM (96 each) | Narrowband PCM / PWM (108 each) |
|---|---:|---:|
| Waveform SSE | 8 / 9 | 3 / 4 |
| Maximum absolute waveform error | 3 / 2 | 3 / 1 |
| Voice proxy | 7 / 6 | 4 / 3 |
| Noise proxy | 6 / 5 | 2 / 2 |
| Period-error proxy | 8 / 8 | 3 / 3 |
| Spectral-shape proxy | 5 / 4 | 0 / 0 |
| Balanced magnitude / temporal error | 0 / 0 | 0 / 0 |
| Valid speech intelligibility loss | 0 / 0 | 0 / 0 |

Held-out wideband P4 at 12 kHz has pooled SSE about 1.2% higher, with peak
error 20,837 → 20,872 PCM units and 20,755 → 21,110 on PWM. Its PWM rail
samples rise 7 → 11 while PCM clipping stays zero. Detailed tables retain
pooled SER/RMSE, peak errors, clips/rails, all eight score groups and every
frequency band, including quiet/unsupported source bands.

Source-noisy high-band envelope/onset aggregate errors fall, but individual
worst-window spikes can rise. Above 4 kHz in wideband, noisy envelope peaks
worsen in one PCM case; onset peaks in one PCM/one PWM case. In narrowband's
3–4-kHz band, envelope peaks worsen in five PCM/four PWM cases, and onset peaks
in four/four. Global worst spikes stay unchanged; this does not erase individual
regressions. No per-record time indices or frame arrays are exported.

## Independent pitch observations

The production antialiased 8-kHz view is distinct from independent native-rate
80-ms/20-ms observations. Neither is validated true F0 or a promise of preserved
perceived gender/timbre. Counts are repeated job/path views with overlapping
windows, not independent physical events.

| Native-rate observations | Wideband | Narrowband |
|---|---:|---:|
| 100-cent matches before → after | 9,114 → 9,113 | 11,332 → 11,343 |
| Individually lost / gained matches | 3 / 2 | 16 / 27 |
| Newly missing voicing | 3 | 16 |
| New half / double pitch observations | 0 / 0 | 0 / 0 |

Wideband therefore has a one-match net loss despite passing the production
count guard. Narrowband improves in total while exchanging individual frames.
Worst tuning A/B paths stay private; held-out findings do not refit V3.

## Controls, current normalization and compatibility

All 28 music/synthetic settings remain included and pass independent admission.
Semantic control reports leave STOI unassessed; the public ABI includes that
mathematical term. A [separate parity audit](control-score-definitions.json)
adds it solely for mathematical guard comparison, without claiming music
intelligibility: all 28 checks pass. The score definitions differ by up to
0.001649, which is retained rather than silently equated.

Current optional normalization prepares input PCM before ordinary V9 encoding.
There is no decoded-output gain field or alternate gain format. Six final
normalization/integration checks pass, but no normalized-level corpus-quality
result is claimed. Earlier gain proposals remain verbatim in the immutable
protocols for receipt/hash provenance; this status supersedes those old pending
items.

The final core based on `69e915d4` preserves the frozen V3 plain path. Current
scalar/SIMD WASM exactly matches frozen native PCM/PWM on **408 main-study
streams** (21,944,496 frames per output domain) plus **four Long streams**
(512,004): **412 streams and 22,456,500 frames total**. Final supported Tiny ASM
and Mega C/ASM cases at public 3/8-kbit/s settings pass all six comparisons with
interrupts active and zero underruns. Quality changes are host-encoder proposals,
not new decoder operations or format fields.
Full image sizes, working memory and scoped timing are in the
[final firmware measurements](firmware-results.md).

The 128,001-sample continuous Long P4/P6 regression retains both incumbents and
passes count/EOF checks. It does not establish bounded memory/runtime for
arbitrarily large files or additional MCU streaming support. The separate
archived Sparse80/2-kbit/s audit losslessly repacks 27 streams to V9 and matches
all exact PCM/PWM goldens; it is not a shared P4/P6 quality improvement.

## Evidence

- [Compact summary](results-summary.json)
- [Full wideband metrics](wideband-results.json), [full narrowband metrics](narrowband-results.json)
- [Peak/noisy-burst tradeoffs](peak-burst-tradeoffs.json)
- [Long regression](long-results.json), [Sparse80 audit](sparse2-audit.json)
- [Public tuning history](public-pilots.json)

API wall totals are 1,734.40 → 2,072.12 seconds for wideband and
900.93 → 1,351.96 for narrowband. These include concurrent bounded work and
are not an isolated speed benchmark or decoder CPU cost.
