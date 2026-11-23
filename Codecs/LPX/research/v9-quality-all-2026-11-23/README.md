# V9 quality across profiles: prospective corpus harness

This directory contains a research driver and independent evaluation code.
Production encoding remains shared C++; Python only prepares references,
orchestrates the native API and measures complete decoded outputs.

Read [the completed results](RESULTS.md), [the original frozen protocol](PROTOCOL.md)
and its [frozen wideband/time-fidelity addendum](PROTOCOL_WIDEBAND.md). Private media, source
identities, fingerprints, provenance, snapshots and detailed receipts remain
under ignored `build/`. Export uses an explicit anonymous numeric allowlist.

The current prospective primary is 24 complete genuine-wideband utterances,
12 from official FLEURS at 16 kHz and 12 from official VCTK at 48 kHz, totalling
134.2185 seconds. Source-only selection freezes eight tuning and 16 held-out
cases. All 24 have a supported band above 6 kHz after direct 16 kHz preparation.
P4/P6 at 12/16 kHz give 96 jobs per encoder. Separate narrowband regression
uses the established 27 complete four-second references at 8 kHz, with P4/P6
and strict 3/8 kbit/s budgets (108 jobs). This is no longer the old 216-job
resampled narrowband proposal. Neither source acquisition nor selection uses
codec outputs. Counts do not imply independent speakers across the corpora.

The baseline is archived from exact public Git commit `f282950c`; never build
it from changing working sources. The driver compiles portable C arithmetic,
WideV9 and actual-rate support with `-O3 -std=c++11 -ffp-contract=off`. Four
search calls, zero size allowance and preserve-level preparation are fixed.
Every stream is decoded completely twice, into PCM16 and fixed PWM, with exact
sample count/rate and termination checks. Original complete caps are reused
explicitly for candidates. Waveform error, magnitude spectrum, spectrogram
changes, high-band envelope/onsets, source-only noisy frames, actual-rate STOI
and source-frozen periodicity are retained separately.

## Reproduction

Commands run from the task worktree; `python` needs NumPy, SciPy and pinned
`pystoi` 0.4.1. Native compilation/execution on Windows uses the installed
Ubuntu WSL GCC toolchain. All arguments below use ignored private destinations.

```text
python Codecs/LPX/research/v9-quality-all-2026-11-23/corpus.py freeze --output build/quality-corpus/frozen-baseline
python Codecs/LPX/research/v9-quality-all-2026-11-23/corpus.py build --output build/quality-corpus/candidate-v2
python Codecs/LPX/research/v9-quality-all-2026-11-23/corpus.py prepare --set pilot --baseline-build build/quality-corpus/frozen-baseline --output build/quality-corpus/pilot-v2
python Codecs/LPX/research/v9-quality-all-2026-11-23/remeasure.py --manifest build/quality-corpus/pilot-v2/manifest-private.json --frozen-results build/quality-corpus/pilot-v1/baseline --output build/quality-corpus/pilot-v2/baseline
python Codecs/LPX/research/v9-quality-all-2026-11-23/corpus.py run --manifest build/quality-corpus/pilot-v2/manifest-private.json --encoder build/quality-corpus/candidate-v2/corpus_driver --phase candidate --baseline build/quality-corpus/pilot-v2/baseline --output build/quality-corpus/pilot-v2/candidate-v2
```

`prepare_wideband.py primary` accepts the independently frozen private source
manifests. Its `narrowband` command reuses exact previously frozen 8 kHz target
bytes. `corpus_audits.py` handles separate genuine-source/Long controls and the
archived Sparse80/2 kbit/s incumbent audit; the latter is not claimed as a
shared P4/P6 quality improvement. Current optional normalization prepares input
PCM before ordinary V9 encoding; there is no decoded-output gain field or new
gain wire format. The quality study preserves source level and makes no
normalized-level corpus-quality claim. Input compatibility is checked separately.

For approved larger runs, `run --shard-count N --shard-index I` makes stable
disjoint shards into the same result directory. `export` merges their completed
receipts and reports whether all prospective jobs exist. Coordinate N with
other numerical work; the team limit is three workers. A native failure,
missing STOI or rejected objective must not disappear from reporting.

## Initial findings

The completed study has **96/96 wideband and 108/108 narrowband jobs passing
independent admission**, with 12 and 11 changed outputs respectively. No file
grows; one 3 kbit/s stream shrinks by four bytes. The formal 8 kbit/s corpus
retains its incumbents, while its public tuning example improves. Gains are
small and uneven: waveform peaks, individual noisy-burst errors and some
voice/pitch diagnostics can regress. See [completed results](RESULTS.md) and
all-metric tables. No audible or all-metric improvement is claimed.

The frozen strict-v1 public pilot had 24/24 valid full native decodes and
24/24 valid independent STOI measurements on each PCM/PWM path. Candidate
outputs equalled the incumbent byte-for-byte in all 24 jobs, so this was a
safety result with no measured quality improvement. API encode time was
84.07 seconds for the incumbent and 114.31 seconds for the candidate. A
separate four-job genuine 44.1 kHz source control also retained all incumbents.
The revised V2 magnitude/time objective is a separate experiment; do not reuse
the v1 safety result as an improvement claim.

The frozen V2 public tuning pilot changed two of 24 outputs: P6 at 12 kHz
and the strict 8 kbit/s preset on one public phrase, at unchanged complete
file sizes. Independent weighted scores fell from 1 to 0.96089 and 0.96396;
PCM STOI rose by 0.00806 and 0.01252. Balanced magnitude and temporal errors
improved on both output paths. This is not an all-metric win: the P6 PCM voice
and noise proxies rose, and the 8 kbit/s PWM rail count rose from six to eight
samples (PCM clipping fell from five to four). Twenty-two outputs retained
their incumbents. Candidate API wall time was 129.01 seconds versus 84.07,
under concurrent bounded work. See [anonymous pilot evidence](public-pilots.json).
These tuning results do not establish audible or broad-corpus improvement.

The final V3 public pilot adds fixed-width spectral pulse proposals under the
same frozen objective, safety rules and original incumbent denominators. It
changes three of 24 outputs, including the 3 kbit/s preset at unchanged 887
bytes. That preset's balanced magnitude/time losses fall about 2.5%, while
waveform SSE rises about 1.15%; this tradeoff is permitted by the revised
magnitude/time goal. All 24 independent admissions pass. The 8 kbit/s and
P6-at-12-kHz weighted scores fall further, while some voice, noise, period
and intelligibility components trade off relative to their V2 selections.
All remain subject to the original-incumbent safety floors. The final genuine
wideband and narrowband runs use this frozen V3, after tuning results and
cross-backend verification, without refitting from held-out results.

A later user decision removes the optional file-gain feature. The primary
preserve-level targets and quality constants stay frozen; no normalized-level
corpus result is claimed. Final-core plain-path compatibility is a separate
integration check rather than a reason to refit quality settings.

The fixed tuning studies are aggregated before their held-out partitions.
Genuine-wideband tuning changes three of 32 outputs, at identical complete
bytes; all 32 independent admissions pass. Its native-rate pitch audit finds
no lost 100-cent matches or new missing/octave observations in changed output.
Narrowband tuning changes three of 40 outputs and passes all 40 admissions,
also at identical bytes. Across its fixed PCM/PWM job views, source-period
observations stay 6,040 and matches rise 4,457 to 4,466. That net count hides
12 individually lost matches and 21 gains: the newly lost observations are
missing voicing, not new octave-down/up observations. Missing observations
fall from 1,500 to 1,491 overall; existing half/double totals stay 38/38.
These are heuristic observations, not validated true F0 or a promise that
every frame improves. Private worst-case A/B paths and time indices are kept
outside tracked evidence. See `pitch_tradeoffs.py` for reproducible masks.

Independent evaluator checks cover phase inversion (equal magnitude/time with
large waveform error), moved high-band bursts (equal global energy with wrong
time envelope), source-mask independence and silence/noise at all three rates.
A separate native/NumPy synthetic oracle covered 25 cases and 50 PCM/PWM paths:
source masks/counts agreed exactly; normalized full-band components differed
by at most 3.6e-14, voice by 3.7e-12, and period/shape by 2.6e-14 or less. This
is numerical verification of the diagnostic, not a perceptual-quality claim.
