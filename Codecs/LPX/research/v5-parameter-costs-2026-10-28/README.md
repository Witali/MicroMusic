# Exact parameter-cost preparation: no new format

Thirteen predeclared parameter sketches were measured on the original
baseline-v2 and selected expanded100 streams for all 49 main recordings/both
profiles, plus all 132 frozen non-speech records/both profiles. This is **460
source/profile groups, 5,980 whole-chain costs and 9,490 segment costs**.
Baseline and expanded views share recordings; the separate robustness corpus
is not claimed to be statistically independent of the main regression set.

No new encoder/decoder format, MCU change, audio output or quality metric was
implemented/computed. These are exact *hypothetical stored byte costs under
explicit assumptions*. They identify parameter-preserving opportunities;
actual future parameter reconstruction, PCM/PWM equality and firmware savings
remain to be implemented and verified separately.

## Frozen tuning-only nomination

The simplest nominated syntax is **repeat-mask1**, scale only:
keep the first tuple absolute, then one scale-repeat flag per later tuple,
reading five absolute scale bits only on change. Lag/gain remain fully absolute.
Among repeat candidates with positive aggregate tuning savings in both source
families, the rule prefers fewer selected fields, then the strongest worst-source
fractional saving. It does not use held-out or robustness costs.

The separately retained higher-complexity point is
**rice-mask5-k1**: Rice k=1 for scale and gain-code deltas, lag still
absolute. Eight-zero escape carries a complete absolute field. It needs exact
previous scale-code state or a separately proved representation; derived
`blockStep_` cannot recover aliases. No code-size benefit is assumed.

Both nominations locked after the 80 tuning source/profile groups and before
the remaining 380 held-out/robustness groups. All thirteen candidate results
remain in the reports; no validation result changed the nominee.

The following signed savings already charge one selector byte **per segment**,
first absolute tuples, mandatory tails and exact independent byte padding:

| Source / split | Profile groups | Scale-repeat savings min / median / max, B | Rice scale+gain k=1 savings min / median / max, B |
| --- | ---: | --- | --- |
| baseline-v2 / tuning | 40 | 5 / 23 / 117 | 25 / 56.5 / 171 |
| baseline-v2 / evaluation | 40 | 3 / 24 / 156 | 17 / 48.5 / 160 |
| baseline-v2 / additional | 18 | 0 / 9 / 146 | 0 / 23 / 296 |
| expanded100 / tuning | 40 | 5 / 22 / 117 | 25 / 57 / 171 |
| expanded100 / evaluation | 40 | 2 / 23.5 / 155 | 17 / 48.5 / 160 |
| expanded100 / additional | 18 | 0 / 8.5 / 141 | 0 / 23.5 / 305 |
| non-speech-baseline-v1 / non_speech | 264 | 9 / 104 / 5371 | -2 / 120 / 7325 |

The large robustness maxima include recordings whose data cannot fit into a
32 KiB ATmega328P image even before program code. `byte-budget-context.json`
separates those cases: five robustness profile groups exceed 32 KiB in original
data alone. Remaining data-only eligibility still does not prove program fit.
No STOI, music quality or perceived-quality inference is made.

## Exact accounting assumptions

Repeat masks cover all 7 nonempty scale/lag/gain subsets. A selected later field
pays one flag plus its old 5/7/3 absolute bits only when changed. The six Rice
sketches select scale+gain or all three fields with common k=0/1/2. Zigzag delta
q<8 costs q+1+k; q>=8 spends eight zero bits and the full absolute field value,
not an escaped delta literal. The escape distinction must be explicit in a
future parser; existing v5 `readSpeechRice` is not assumed to be a free drop-in.

Each segment begins with all 15 absolute parameter bits. Every stored tuple is
preserved, including unplayed last packets and lag when gain is 0. Scale aliases
are not normalized. Histograms retain actual code units, transitions and
segment resets; they separate stored from audible tuples.

The existing source stream is never canonicalized for attribution. An actual
bit cursor counts its full consumed v5 payload, retaining original spectral
Rice choices, extras flag and every marker. Only the 15-bit tuple fields are
replaced in the hypothetical cost. A set extras flag with no active pulses and
even a legal marker 1 / amp 0 remain charged. Actual source padding is removed only
to calculate the new exact final padding for **each segment**, not one padded
concatenation of a recording.

The charged fixed overhead is 22 existing header bytes plus 1 method-selector
byte, reported as 23 overhead bytes in the counter. Proposed payload-bit columns
refer to the remaining bit-packed body. This accounting does not finalize the
selector's physical placement or silently reuse v5 flags. A new version/syntax
would be required.

## Byte allowance versus firmware saving

`whole_stream_saved_bytes` is signed. It is an **optimistic UPPER BOUND** on what
the data saving alone could pay for added decoder code, tables and layout in
that recording's image. It is not a measured net Flash reduction. Zero-byte
phrase cases cannot pay any positive program growth. A negative cost case needs
savings elsewhere merely to break even. Corpus totals are benchmark totals,
not an affordable code budget for one firmware image.

The optional per-segment `min(v5,new)` envelope is even more optimistic: it
ignores the program cost of supporting both formats. Uniform new-format costs
are the primary figures and drive nomination. All actual program Flash, SRAM,
stack, C fallback, malformed-input/lifetime behavior and active-IRQ timing
remain future acceptance requirements.

## Untested minimal-state design option

The already charged selector could sit at the start of a new version's payload,
included in the existing uint16 payload length. Storage remains 22 + 1 + body and
padding is identical. A scale-repeat-only prototype could validate selector 1
once and discard it, retaining `blockStep_` on repeats. No per-stream dynamic
method or raw scale-code member is required by that restricted design.

The existing **decoded** `lag_ == 0` sentinel distinguishes the first v5-style
tuple: `resetState()` sets it to 0, every `begin()` calls reset, and every valid
tuple stores 18..145, even for gain 0. Sample that state before assigning the new
lag; encoded lag code 0 itself is valid and means lag 18. Failed begins/sticky
errors and value copies must retain their existing contracts. This domain does
not apply to legacy raw v2/v3 modes where lag can remain 0 after output.
`blockStep_ == 0` is not a valid first-tuple sentinel because legal scales 0..5
all map to 0; scales 6..9 also alias to 1.

This is an **UNTESTED design hint**, received after cost nomination, with no
Flash/SRAM claim. Before any prototype, inspect all compact/version 5 branches,
host parsers, header bounds, reset/copy/error paths and existing-format fallback.
The measured-cost nomination remains independent of that implementation idea.

## Audit and reproduction

Nine focused cost/histogram groups pass. An independent indexed cursor and
existing BitWriter checked all 9,490 segment parameter/size calculations and all
5,980 complete chain rows. All 726 unique current v5 sources matched the existing
serializer with their **original** extras flag. Stored/audible repeat and delta
histograms were independently verified. Synthetic forced-empty partial tails
and legal zero-amplitude markers protect cases not present in this sample.

`chain-costs.csv` and `segment-costs.csv` are lossless scalar projections of the
audited costs; `histograms.json`, `summary.json` and `nomination.json` retain
source/split/cohort/profile separation. Private input paths, identities, audio
and per-recording fingerprints remain ignored. Source/runtime and exact measured
reproduction scripts are retained. The study took 26.69 s;
the independent audit took 39.96 s. No native decoder or target
firmware benchmark was run for a new format because none exists yet.

Run from the repository root with Python 3.12, the package versions in
`source-runtime.json`, and locally supplied frozen manifests/receipts:

```sh
python Codecs/LPX/research/v5-parameter-costs-2026-10-28/reproduction/study.py \
  "$LPX_BASELINE" "$LPX_NONSPEECH" "$LPX_TUNING_EXPANDED" \
  "$LPX_EVALUATION_EXPANDED" "$LPX_ADDITIONAL_EXPANDED" \
  --output build/parameter-cost-replay
python Codecs/LPX/research/v5-parameter-costs-2026-10-28/reproduction/audit.py \
  build/parameter-cost-replay \
  Codecs/LPX/research/v5-parameter-costs-2026-10-28/reproduction/study.py \
  build/parameter-cost-audit
```

No external upload is needed. Keep generated private receipts under ignored
`build/`, and do not use Python optimization flags: shared validation uses
assertions. Code/counter origin: `1e5b49b9`; unchanged MCU source: `5c7e0592`.
