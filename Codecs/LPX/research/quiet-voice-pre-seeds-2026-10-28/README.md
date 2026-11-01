# Original-level quiet-voice seed controls: before the zero-scale option

This is retained evidence from the **old encoder epoch**, not the new voice
frontend's corpus admission. Every fit used original-level, full-length PCM
with no gain fitting or output amplification. The pre-grid uses encoder
`9ad3685c`; `allow_zero_scale` did not exist or participate. The separate
`576ef6c3` fix must not be credited with these results.

The target clip is now a **user-targeted diagnostic** following reported voice
character loss. It is not independent held-out evidence for these experiments.
Its RMS is 27.61 PCM16 units, about -61.49 dBFS, with peak 306. The frozen source
diagnostic finds 77 reliable candidate-period windows out of 197 complete
80-ms windows. A missing output period is a failure or unknown result, never a
passing pitch score. These diagnostics and the voice objective are proxies;
neither validates true F0, perceived identity nor subjective quality.

## Target: all 15 saved alternatives

[target.json](target.json) retains every alternative, both original A/B
baselines, original-byte/95%-cap flags, old PCM/PWM SSE/STOI gates, source-bound
voice diagnostics and the separately frozen voice objective. All 15 alternatives
fail at least one original automatic metric floor. None is automatically
adopted. Profile 6 uses 719–724 extra bytes, exceeding the original 1,800-byte
cap; no acceptable firmware or data-growth policy is inferred.

| Target control | Bytes | Reliable paired periods / source 77 | Fixed source-period output error | Voice objective, lower is better |
| --- | ---: | ---: | ---: | ---: |
| Original baseline | 1,800 | 0 | 0.5813 | 3.2053 |
| Existing smaller baseline | 1,701 | 0 | 0.5797 | 3.2417 |
| Fresh profile 4, pre 13926 | 1,698 | 0 | 0.5801 | 3.3927 |
| Fresh profile 4, pre 8192 | 1,702 | 0 | 0.4777 | 2.8796 |
| Fresh profile 4, pre 0 | 1,701 | 0 | 0.4228 | 2.5249 |
| Fresh profile 6, pre 13926 | 2,519 | 12 | 0.2980 | 0.9541 |
| Fresh profile 6, pre 8192 | 2,520 | 23 | 0.2764 | 0.9861 |
| Fresh profile 6, pre 0 | 2,524 | 19 | 0.2667 | 1.2101 |
| Pre 0, all-block periodic reseed, original gains | 1,701 | 14 | 0.3223 | 3.0312 |
| Pre 0, only pitched blocks refitted | 1,701 | 7 | 0.3241 | 3.5691 |

The omitted table rows remain in JSON: three fixed-spectrum residual probes,
three incumbent reseeds and the second all-block pre-0 gain control. A fresh
pre-grid consistently reanalyzes the spectrum for each header. The residual
probes instead freeze the incumbent spectrum and remove extras. The incumbent
reseeds retain its filters, spectrum and extras. These are distinct controls,
not interchangeable legacy runs.

The periodic local weight 8 follows the frozen objective's periodicity/waveform
ratio 2/0.25, with a 320-sample local horizon. It is proposal generation only.
Lower fixed-period error can coexist with worse full-record waveform error or
STOI; the full voice objective also penalizes several such alternatives.
Profile 6 materially improves native PCM proxies, but many output periods
remain missing and the original-level 8-bit PWM results remain weak. PCM and
PWM metrics are separate in every row. No arbitrary quiet-signal preservation
or physical-output claim follows.

## Level-selected tuning control: all 18 fits

The selection used input levels only: among 20 tuning references, take **both
with RMS below 256 PCM16 units**, plus the median-RMS tuning source. The quiet
levels are 96.89 and 102.66; the normal control is 1,548.57. Full source lengths
are 64,000 / 32,000 / 64,000 samples. Both profiles and the unchanged pre-grid
13926 / 8192 / 0 produce 18 fits. These are tuning data, not a validation split.

[tuning.json](tuning.json) retains every candidate, all six profile incumbents,
old cap/floor failures and complete metric domains. Exactly three candidates
fit the old full byte cap and preserve all old PCM/PWM SSE/STOI floors:

| Quiet case 1 | Old → new bytes | Old → new voice objective | Old → new reliable paired periods / 154 source windows |
| --- | ---: | ---: | ---: |
| Profile 4, pre 8192 | 1,806 → 1,697 | 0.53319 → 0.38969 | 69 → 88 |
| Profile 6, pre 8192 | 2,621 → 2,517 | 0.30974 → 0.18736 | 114 → 127 |
| Profile 6, pre 0 | 2,621 → 2,516 | 0.30974 → 0.19378 | 114 → 133 |

The other quiet case has useful raw voice proxies but no admitted old-floor
candidate. Its profile-6 pre-8192/pre-0 data also exceed the old cap by 1/4 bytes.
The normal control prefers legacy pre-emphasis among fresh seeds, and all its
fresh seeds fail the stronger incumbent floors. A blanket pre-0 default is
unsupported. The original runner wall time is 56.42 seconds, including metrics, native
validation and I/O; no matched pure-search speed or MCU-runtime comparison is
claimed.

## Read-only saved-output audit and source limits

After fitting, a read-only audit checked 41 stream bindings: 15 target variants,
two target baselines, 18 tuning variants and six tuning baselines. Every saved
WAV matches the model and both native layouts in PCM16 and PWM: **164 native
output-domain comparisons / 7,296,000 sample-domain comparisons**. Bindings are
not asserted to be unique or statistically independent streams. The 18 tuning
metrics/objective values reproduce within 1e-12. No new fit, variant, AVR image,
IRQ experiment or board measurement was performed to export this evidence.

All rows use the same read-only measurement epoch: standard metrics/model from
`9ad3685c`, voice diagnostic `065716f5`, objective `61f96e62`, unchanged decoder
`5c7e0592`. Early exploratory diagnostic values may predate the final pitch
interpolation correction; retained output bytes are evaluated consistently
here. [source-runtime.json](source-runtime.json) binds exact source files and
the retained original runner bytes **after the runs**. It does not establish
pre-run or original-run mutation attestation. Private manifests, original
names/paths, recordings, codec/PCM/firmware hashes and generated outputs remain
in ignored storage.

Exact retained scripts cover the inverse-force probe, original pre-grid,
18-fit tuning grid, final pre-0 reseed and pitched-only prototype. The early
incumbent reseed runner versions were edited in place before archival: their
exact original source bytes/hashes are unavailable. The profile-6 pre-grid was
an in-memory wrapper around the retained pre-grid script. These invocation
reconstructions are labeled, with no invented original hashes.

## Parameterized source projections

The scripts under [reproduction/](reproduction/) remove local paths, add shared
source/output guards and use explicit local data/tool locations. They are
**public projections**, not byte-identical executed runners. Their hashes and
differences are recorded. Only syntax and CLI help were checked while saving;
their fitting paths were not rerun. Existing original scripts remain archived
privately. A later reproduction needs matching frozen source files, packages,
the local corpus/target and native compiler; outputs must stay in a fresh owned
directory under this checkout's ignored `build/`.

Example for a later explicitly authorized reproduction, with local paths in
environment variables:

```sh
python reproduction/pre_controls.py --mode tuning \
  --codec-tools "$LPX_TOOLS_9AD" --voice-tools "$LPX_TOOLS_065" \
  --objective-tools "$LPX_TOOLS_61F" --manifest "$LPX_PRIVATE_MANIFEST" \
  --output build/quiet-pre-replay
```

`reproduction/` above denotes this folder's subdirectory. `pre_controls.py`
also has target mode; `residual_seeds.py` records the fixed-spectrum inverse
experiment; `reseed_controls.py` reconstructs the original/pre-0/pitched-only
settings using the published `41f57496` component. They require the **old**
encoder file, not the new zero-scale frontend. Source/gain choice and a new
frontend corpus study are separate work.
