# New-encoder non-speech robustness: all 132 references

All **132 non-speech references / 264 profile groups pass** the frozen bounded
NEW-encoder search and a fresh independent saved-output audit. This is more than
baseline playback: 231 selected encoded chains change, and 230 reconstructed
PCM outputs change. Complete original references, gain and reset geometry are
preserved. No STOI, subjective music-quality/adoption or hardware claim is made.

The profile-group total is **25,111,466 samples**, covering each source in
profiles 4 and 6. Lengths range from 10,400 to **3,786,111 samples**. The
494 original reset segments include 60-, 50- and eight-segment long chains;
no output is truncated at 64,000 samples. The same 132 references appear in
both profiles, rather than representing twice as many independent sources.

## Predeclared protocol

Before candidate outcomes, choose the original segment with the largest exact
PCM SSE/sample, earliest index on a tie, and the final segment when distinct.
This produces **268 searched segments** and **226 untouched segments**. Every
untouched segment stays byte-identical and is independently decoded too.

Every search uses exactly the fixed recipe: two anchor windows, two adjacent
frames, beam 2, two spectral finalists, one excitation finalist, horizon 80,
64 complete evaluations, local screening 640, amplitude capacity, lambda 0,
conservative numerical PCM/PWM floors and `speech=False`. Each edited segment
is capped at its actual original complete bytes; the true full-chain cap is
checked again after joining every reset segment/header.

The objective uses exact additive whole-record SSE substitution. It returns
candidate-segment SSE minus original-segment SSE, removing the large constant
before the refiner's float score. The frozen whole SSE plus that integer delta
is the exact whole candidate error. Segment deltas stay exactly representable;
whole totals use bounded int64 dot-product chunks accumulated in a Python
integer. A 3.79M-sample recording is not rebuilt per trial. Final full-record
metrics are independently recomputed from saved streams, not inferred from
these predicted deltas or optimizer snapshots.

A geometry-only smoke chooses shortest and longest source cases, both
profiles, before the full outcomes. All four smoke groups pass, including
complete 60-segment output. Full-run selected/raw byte sequences reproduce
the smoke exactly. The complete run uses three deterministic ordinal shards
with 88 groups each and an unchanged source/settings/manifest fingerprint.

## Observed numerical outcomes

| Observation | Profile groups |
| --- | ---: |
| Selected encoded chain differs from baseline | 231 |
| Selected PCM differs / PCM SSE strictly decreases | 230 |
| Selected complete PCM and PWM numerical floors pass | 264 |
| Raw complete PCM and PWM numerical floors pass | 245 |
| Raw PWM SSE regresses (separate tradeoff retained) | 19 |
| Selected complete stream becomes smaller | 26 |

Selected byte savings span 0–4 B per complete chain. These are actual
serialized bytes, not a prediction from an objective scalar. All raw PCM SSE
values are non-increasing, but 19 raw PWM errors increase; those raw alternatives
remain explicitly labeled. Numerical changes do not establish an audible
benefit or a music-quality percentage.

The run performs **17,152 complete synthesis evaluations**, 18,901 local
probes and 1,190,736 local excitation trials. All 268 searches reach the fixed
64-complete-evaluation bound. There are 184 completed adjacent-frame windows
and 268 interrupted windows; some requested work is therefore unfinished.
These finite settings establish bounded robustness, not convergence, an
optimum, or exhaustive quality improvement.

Direct original-level descriptors are retained per group for the reference,
baseline, selected and raw outputs: RMS, peak, full-scale sample fraction,
nonzero fraction, absolute-amplitude >=256 fraction and fixed-PWM endpoint
fraction. The activity threshold is not VAD; full-scale occurrence is a
descriptive proxy rather than proof of source ADC clipping. No shortening,
resampling, gain normalization or delay alignment is applied.

## Independent audit and scope

A separate fresh-process auditor reopens original references and actual saved
selected/raw segments. It independently derives the original worst-SSE/sample
choice, reconstructs every distinct complete baseline/selected/raw chain, and
compares full PCM16 **and PWM** on native common and compact-only decoders
against the independent model. It recomputes complete metrics, descriptive
levels, original length/level, per-segment caps and whole-chain caps, and checks
input/source identity and private artifact hashes. All **264 audit groups pass**.
A regression test deliberately corrupts a stored metric and confirms rejection.

These are host results with unchanged v5 syntax and MCU source. Five original
complete data chains exceed 32 KiB **before code**, and the largest has
299,058 encoded bytes. No image is built or hardware admission asserted for
this study, including for shorter chains. Target Flash, SRAM, stack and active
IRQ support would require their own complete-image validation. No STOI is
computed or interpreted for this non-speech set.

## Reproduction and anonymous evidence

The [fixed protocol and CLI commands](../../01_ACTIVE_Q0_CODEC/tools/NON_SPEECH_ROBUSTNESS.md)
cover smoke, full deterministic shards and independent output audit. Source
commits are `e30ed737` (harness) and `fd8e3021` (independent auditor), following
metric-mode change `509db927`. Six harness groups plus 17 refiner groups pass;
the original speech-policy tests remain unchanged.

[Summary, exact bounds and public source/runtime versions](summary.json) and
[all anonymous group metrics/descriptors/search/window evidence](groups.json)
contain no original names, paths or media-derived fingerprints. Full references,
streams, original IDs, PCM/PWM hashes and private run/audit manifests remain in
ignored build storage. Process CPU totals include original/final decoding and
metrics; timing is descriptive and is not a target-CPU or listening comparison.
