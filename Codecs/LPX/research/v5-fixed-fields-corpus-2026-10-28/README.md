# Frozen fixed-fields v5 corpus control

This study applies the frozen bounded optional-pulse policy to **49 recordings,
both profiles: 98 profile groups and all 294 original-cap rows**. It changes no
MCU source or v5 syntax. Decoder sources match the frozen baseline inventory
from `5c7e0592`; host program-Flash benefit is **0 B**.

Settings were fixed before this run: amplitude seed, at most 128 full renders,
32-candidate batches, SSE objective/lambda zero, and the amplitude-control four
quality floors. Tuning, evaluation and additional cohorts use exactly the same
settings. No settings were retuned on evaluation/additional outcomes. Joint LPC
changes and nonzero-lambda sweeps are outside this control.

## Complete-recording results

The cap is `floor(original_complete_stream_bytes * percent / 100)`. It includes
every segment header, stored final packet, extras marker and padding byte. These
are encoded reset-chain byte caps; full linked MCU player Flash/IRQ admission
remains a separate measurement.

| Cap | Amplitude fits | Accepted swap fits | No finite-pool fit | PCM SSE better / equal / worse versus same-cap amplitude | Accepted passing original-incumbent four floors |
| --- | ---: | ---: | ---: | --- | ---: |
| 100% | 98/98 | 98/98 | 0 | 0 / 98 / 0 | 98 |
| 95% | 79/98 | 79/98 | 19 | 26 / 53 / 0 | 0 |
| 90% | 30/98 | 30/98 | 68 | 5 / 25 / 0 | 0 |

Across common fitting profile groups, summed PCM error energy changes by
-0.3296% at the 95% cap
and -0.1674% at the 90% cap
versus amplitude controls. At 100% it is unchanged.

Every accepted output preserves the *complete-recording* amplitude control's
PCM/PWM SSE and available STOI floors. This does not imply a gain against the
larger original incumbent. `rows.json` contains full original-incumbent,
amplitude, accepted-swap and raw-swap PCM/PWM metrics, actual bytes and original
floor flags. The raw result can fail amplitude or original floors; it remains a
research/listening alternative. All automatic-adoption flags are false.

The last table column checks the returned accepted output against the original
incumbent. `observed_original_selected` is a separate best qualifying point
among returned shortlist/frontier snapshots. It does not claim a global optimum
over every unmeasured combination. The original incumbent is always preserved
as rollback even when it lies outside a smaller cap.

Same-cap quality comparisons may spend a different number of bytes within the
same total cap. Equal achieved byte counts are reported separately:

| Cap | Equal achieved bytes | PCM SSE better / equal / worse at equal bytes | Accepted uses fewer bytes | Accepted uses more bytes within cap |
| --- | ---: | --- | ---: | ---: |
| 100% | 98 | 0 / 98 / 0 | 0 | 0 |
| 95% | 79 | 26 / 53 / 0 | 0 | 0 |
| 90% | 30 | 5 / 25 / 0 | 0 | 0 |

Error-energy percentages describe measured error, not perceived-quality
percentages. Group aggregates sum actual full-length error energies across
common fitting cases. Non-speech STOI is retained as a mechanical gate/metric,
not interpreted as music intelligibility.

## Frozen proposal and selection protocol

Spectra, scale/lag/gain, mandatory pulses, pre/bright filters, samples and reset
boundaries stay frozen. Only membership of the original optional extras can
change. Each segment gets a finite proposal cap grid: original bytes; actual
serialized sizes with 0/25/50/75/100% active extras; 90/95/100% segment bytes;
and requested whole-cap residuals against other segments' baseline/minimum
fixed-field bytes. Out-of-API and redundant proposals remain in the grid report.
These are generation caps, **never proportional final admission**.

The preserved amplitude fit supplies each proposal's control. Bounded swaps
exchange one retained and one removed original extra at unchanged stored rate.
Accepted states are actually serialized and reconstructed again; subsequent
proposals use the new state. Duplicate identical amplitude seeds reuse only an
equivalent frozen search; reused renders are counted as zero and traces match.
Generation no-fit and evaluation-limit outcomes are kept in `generation.json`.

Proposal quality gates replace just that segment in the original complete
reset chain. Since the objective is SSE, its fixed other-segment contribution
can be added exactly; STOI/PWM gates still use the complete concatenated output.
The complete amplitude pools are then assembled under each true total cap.
Merged swapped pools use that fitting whole-chain amplitude result as rollback
and quality baseline. Final outputs are re-scored on the full original reference
with original gain/length and decoder resets. No local cap or segment-local
floor decides final admission.

The shared selector enumerates finite pools when possible, otherwise reports
its bounded 32-wide/4096-evaluation beam. It preserves cheap feasible
continuations and limits the returned size frontier to 16 points. Its metric
admission scope is the objective shortlist, frontier and feasible rollback.
Every limit/no-fit row is retained; these finite-search results cannot establish
that a different spectrum or v5 stream cannot fit.

## Source and independent audit

Sixteen focused test groups passed before the run. The independent audit then
re-read every original reference, ordered segment and generated artifact, and
verified current native **common and v5-only PCM/PWM** against the full integer
model. It reconstructed accepted intermediate swaps and rechecked their exact
scores, constant rates and four floors. Whole-chain roles were independently
reconstructed and re-scored again.

The audit checked 1581 unique streams,
966 accepted intermediate
states and 817 returned complete-chain
points. All source/runtime/input guards passed. Per-record source/artifact
bindings, reference/audio fingerprints, private identities and paths remain
only in ignored receipts; published rows use anonymous case/profile identifiers.
`source-runtime.json` pins public source, native library and package provenance.

The resumed three-worker campaign took 656.61 s
wall time and reused one source/artifact-verified tuning smoke record. Per-record
measured wall sum is 1498.57 s and measured
process CPU sum is 1483.92 s. CPU
includes in-process native decoding, NumPy/SciPy/Numba DSP and metrics; excludes
compiler subprocesses/coordinator/startup. Wall sums include validation and I/O,
so these are campaign costs rather than a matched isolated-search speedup.
The separate audit took 412.52 s.

## Reproduction

Run from the repository root with Python/package versions in
`source-runtime.json`, a native C++ compiler, and the locally supplied immutable
`lpx-v5-encoder-quality-study-v1` baseline-v2 manifest/files. The scripts in
`reproduction/` are exact copies of the measured/audited source, including the
same fixed settings. Provide a fresh ignored output directory:

```sh
python Codecs/LPX/research/v5-fixed-fields-corpus-2026-10-28/reproduction/corpus_control.py \
  "$LPX_MANIFEST" build/fixed-fields-replay --workers 3
python Codecs/LPX/research/v5-fixed-fields-corpus-2026-10-28/reproduction/audit_and_export.py \
  "$LPX_MANIFEST" build/fixed-fields-replay build/fixed-fields-audited \
  Codecs/LPX/research/v5-fixed-fields-corpus-2026-10-28/reproduction/corpus_control.py
```

The native compiler belongs on PATH; shared Python dependencies may be supplied
through PYTHONPATH. The driver adds the repository tools directory itself.
Fresh runs bind their actual compiler-built native libraries and source-file
labels; existing cache receipts require the identical source/runtime identity.
Every cache hit remains provisional until the mandatory independent audit
rechecks current references, input streams, outputs and metrics. Do not run with
Python optimization flags: validation uses assertions in the shared model/tools.
Generated media/private receipts stay under ignored `build/`; no external upload
is needed. Actual whole-player Flash, SRAM and active-IRQ admission of newly
selected corpus streams is separate and is not claimed here.
