# Low-bitrate quality development, round 2

This round continues the completed [compact-quality study](../README.md).
P3 and strict2k remain different profiles and formats, with different corpora.
Only same-source paired changes within each study are comparable. No decoder
arithmetic, tables, parser, source gain policy or new wire format is introduced.

## Automatic P3 candidate

The C++ accuracy encoder now has an optional final candidate phase. It first
finishes the previous complete P3 result, then uses that file's ACTUAL bytes as
its ceiling. One existing `encodeThreeK` call proposes a fine-grid physical
stream. The unchanged production selector decides whether to use it. The strict
capped-retention research diagnostic is reported separately; no octave rule,
loss weight or existing selection threshold was relaxed.

The phase is enabled in this experimental branch for reset P3 at 8 kHz,
calls4, 1..64000 samples and null prefix. Other rates/levels/call counts, Long
and streaming prefixes retain the previous path. Set
`LPX_ENCODER_COMPACT_ENSEMBLE=0` to reproduce the preceding encoder. Existing
quality/joint-search disable switches also disable this phase. A selected
fine stream retains host accuracy4 through packing; forcing accuracy3 again
would lose the candidate's transmitted precision. Wire syntax remains P4.

The complete prior result remains available on failure or rejection. The
optional `CompactEnsembleReport` records its own status, actual B0, one-call
search work and complete selection counters. It preserves legacy report/error
semantics. The optional C++ raw-proposal capture is cleared on entry and never
reuses another call's output. Existing C exports remain unchanged.

The [registered protocol](P3_PROTOCOL.md) separates the four old development
clips from eight reserve sources. A source-only audit selected six VCTK voices
disjoint from the previous 18 used voices, and two FLEURS recordings. Their
native hashes appeared only in acquisition/transfer records among inspected
records, with no prior encoding-job results. This is the scope of heldout
status, not a proof of complete project-wide novelty.

Official provenance: [VCTK 0.92](https://datashare.ed.ac.uk/handle/10283/3443),
J. Yamagishi, C. Veaux and K. MacDonald, University of Edinburgh (2019),
[CC BY 4.0 license](https://datashare.ed.ac.uk/bitstreams/956a1688-0b59-428c-8a2f-10837433dde3/download);
and [Google FLEURS](https://huggingface.co/datasets/google/fleurs), whose dataset
card specifies CC BY 4.0. Selected recording identities remain local.

Targets are direct native-to-8k resamples using the pinned existing project
routine, fixed first four seconds, preserve level, no trim/alignment/gain fit.
All eight targets are 32000 samples. Source identities, paths, fingerprints,
payloads and full journals remain ignored. Public reserve results contain
anonymous numerical summaries. Development and reserve outcomes are separate.
STOI eligibility is fixed from each disabled baseline for all variants; an
eligible missing score makes that mean unavailable instead of shrinking its
denominator. Unassessed cases remain in byte/error/case totals.

The complete 24-case matrix and independent audit pass. Reserve results below
include all eight sources in each target, with fixed STOI membership:

| Target | Selected changes | Complete bytes, before / after | Mean active STOI, before / after |
| --- | ---: | ---: | --- |
| PCM | 4/8 | 11,783 / 11,738 | 0.694101 / 0.717036 |
| PCM + PWM, reported PWM | 5/8 | 11,774 / 11,720 | 0.678467 / 0.705798 |

No selected active-path SSE, old noise or clipped-sample count increases on
this corpus. This is numerical evidence on eight reserve recordings, not a
blinded listening result or a universal claim about perceived quality. All ten
selected development/reserve cases still fail the separate strict capped-band
retention diagnostic; the production selector and octave guards are unchanged.
The separate [posthoc band diagnostic](selected-band-diagnostics.json) covers
all 16 reserve outputs, 24 active case-paths and 96 supported global 1-kHz band
entries. It finds zero supported-band magnitude-error regressions, aggregate
floor failures or newly added relative octave labels. Capped retention drops
in 38 reserve band/path entries; this energy proxy is distinct from magnitude
error. These are whole-file band and aggregate temporal measurements, not a
guarantee for every frequency bin, local window or perceived sound.

On development clips, PCM remains unchanged. Vinni PWM is now automatically
selected at 1,080 instead of 1,083 bytes; four-file PWM totals change 2,817 to
2,814 bytes and mean PWM STOI 0.638320 to 0.657961. Chego's raw460-byte candidate
remains rejected by the existing octave guard. Its earlier one-listener
preference does not enter reserve means or validate strict2k sound quality.

One reserve recording's raw return is level-unsafe under both targets. The
optional stage reports UnsafeCandidate and keeps its exact successful prior
outputs. All 24 full encodes succeed. These two safety rollbacks are retained
in every denominator, not omitted as failed examples.

Independent evidence covers 216 artifact hashes, 40 distinct fresh native
PCM/static-PWM/EOF/metric/bit/grid replays and all eight original development
switch-off LPX/PCM identities. Reserve source bindings remain private in the
ignored journal. See [complete results](results-matrix.json) and the recorded
[reporting correction before reserve measurements](REPORTING_NOTES.md).

The [listening exporter](make_listening.py) wraps the fixed FIRST reserve PCM
case in three local WAVs: reference, previous and selected output. It selects
ordinal0, rather than the maximum-gain example. Complete LPX size changes from
1,487 to 1,474 bytes. The verified mono PCM16/8k payloads have no fitted gain,
delay or post-decode resampling. Files stay in ignored
`build/compact-quality/round2/listening-reserve-00/`. This posthoc listening
sample does not alter the frozen criteria or measured reserve results.
Use `--case vinni-pwm` for the Russian development comparison in
`build/compact-quality/round2/listening-russian-vinni/`: 1,083 to 1,080 bytes,
fixed duty-average WAV model and the same unchanged source level. The supplied
development example is not counted as independent reserve evidence.

Sum of whole reserve encode wall times is 56.48 to 103.29 s for PCM and
85.80 to 135.82 s for PWM. The extra search costs encoding time. These are
single-run host observations with concurrent research work; they are not
controlled speed ratios, isolated phase timings or decoder-load measurements.

## Joint scale/gain and pulse search at strict2k

This experiment starts from each latest admitted exhaustive output of the
previous 27-case study, including all three prior changes. Its actual B0,
saved prepared target and declared level remain fixed. All previous receipts,
targets, original groups and ten-case heldout membership are verified before
new search; fresh model/native metrics and band matrices must agree exactly.

In each of two selected complete frames it considers two scale/gain states
and a common frozen three-symbol pool for each of four innovations. All
`2 * 2 * 3^4 = 324` leaves use true incoming state and the complete suffix.
Only existing scale/gain/pulse bit fields change; lag, spectra, filters,
padding, nonminimal legal Rice spelling and all other bits remain exact.

Two two-sweep block-coordinate controls use the SAME Cartesian points and
the SAME full-suffix PCM-SSE objective, in opposite metadata/pulse orders.
Each arm has its own twelve-proposal complete-quality cap and retains the
same baseline outside selection. Strict PCM/PWM error/STOI, voice, clipping,
PWM band/burst/every-tail floors and both old joint objectives are unchanged.
Coordinate wins are not mixed into joint outcomes.

The [registered protocol](sparse2-joint/PROTOCOL.md) fixes the work and source
binding. A [synthetic recurrence witness](sparse2-joint/SYNTHETIC.md) verifies
a real coordinate-local minimum that joint search escapes, with no earlier
prefix/full-suffix objective confound. This establishes a mechanism, not a
speech-quality claim. Any admitted pulse-only point must remain distinguished
from actual parameter/pulse coupling in the posthoc attribution.

All 27 cases completed. Joint search and both coordinate controls each admit
the SAME two heldout speech leaves, with no tuning/quiet/noisy/negative-control
changes. All outputs retain their own exact latest B0; total size stays
24,637 bytes. Both new leaves change metadata AND pulses: scale in two cases,
gain in one. Each coordinate arm also queried, queued, selected and returned
those exact leaves. Thus the corpus shows no exhaustive advantage over the
same-objective coordinate controls, despite the synthetic rescue witness.

| Ten-case heldout speech metric | Latest prior baseline | New joint/coordinate output |
| --- | ---: | ---: |
| PCM STOI | 0.7423765521 | 0.7424610061 |
| PWM STOI | 0.7100146367 | 0.7100509058 |
| PCM summed-energy SER, dB | 3.99895272 | 3.99975321 |
| PWM summed-energy SER, dB | 3.97680915 | 3.97766787 |

The incremental gains are tiny numerical changes: PWM STOI +0.00003627 and
SER +0.00085872 dB. No new strict2k listening preference or audible improvement
is established. The exhaustive operator remains experimental; the coordinate
controls reach the same admitted results here. Sharing a precomputed grid
does not measure standalone coordinate CPU cost.

Sum of per-case wall times is 704.01 s: search 582.96 s, admission 111.37 s,
plus other per-case persistence work. The 972 per-arm complete proposal
attempts share 377 actual complete metric evaluations. Final artifact/native
validation and posthoc attribution are separate from those encoding totals.
See [complete anonymous results](sparse2-joint/results-matrix.json),
[attribution](sparse2-joint/attribution.json) and the
[final validation receipt](sparse2-joint/validation-matrix.json). The validator
passes all 8,748 field/grid/label checks, 108 coordinate tables, 81 own-arm
raw/queue/final-floor checks and 57 unique native/model replays with fresh SSE
and changed-sample counts. It regenerates anonymous aggregates and attribution;
full speech metrics are audited from immutable generation receipts rather
than independently remeasured. Validation took 86.44 s separately.

## Verification and practical limits

The independent P3 gate passes four groups: physical relabel/native/odd-grid
checks; exact eligibility/boundary/switch checks; selector/rollback/cache
contracts; and full synthetic/C API/alias cases. Twenty excluded-output and
legacy-counter fingerprints match across enabled/disabled builds. See
[the measured test record](INTEGRATION_TESTS.md).

The [native portability check](check_portable.py) passes two no-exception,
no-RTTI object builds, recorded in [portable-validation.json](portable-validation.json).
The installed host libstdc++ rejects freestanding vector support. No local
Emscripten/WASI SDK/linker was available, so this is NOT a WebAssembly link or
execution result. No shipped Web UI binaries are rebuilt or deployed here.

The joint operator's four synthetic groups pass both native C receivers via
the explicit unchanged v8-to-v5/P6 expansion bridge, including all 324 leaves,
gain-code edges, saturation, real carried state, nonminimal spectra, malformed
patches and real partial tails. The native servers do not parse v8 directly.
Existing first-study experimental source files, protocols, reports and stored
artifacts stay frozen; the intended host accuracy integration is the production
change in this round.

Whole enabled/disabled P3 encode times are reported; exact isolated optional
phase time is unmeasured. No timer or OS hook is added to the portable library.
Single-run host costs are not controlled hardware speed ratios. Changed data
can change AVR work despite unchanged decoder source. These checks establish
no new ATtiny88/ATmega328P IRQ/underrun, physical-board or general audible-quality
guarantee. Private audio and all generated media remain in ignored storage.
