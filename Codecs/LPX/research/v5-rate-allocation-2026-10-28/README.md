# V5 marginal bits: exact search, fitting control and bounded swaps

This is encoder-only work on unchanged v5 syntax and decoder `5c7e0592`.
Shared accounting and exact marginal removal are in `9948ae16`; the separate
feasibility-preserving swap policy is in `5865df33`. Parameter measurements are
in `b17b0876`. No MCU source or format was changed, and no program-Flash saving
is claimed from host code.

These pilots use SSE with lambda zero. Shared complete-bit `D + lambda * R`
accounting is available to the trajectory search, but a nonzero-lambda joint
spectral/excitation sweep is separate combined-study work.

The small pilot shows a useful distinction: exhaustive fresh marginal rankings
can improve distortion per achieved byte, but can exhaust their render budget
before fitting. Starting from the fitting amplitude control and testing bounded
swaps preserves its byte feasibility and can improve that control. Neither
finding is an automatic replacement for the larger original incumbent.

## Scope and roles

Six tuning recordings were selected by a fixed rule: the shortest eligible
one-segment recordings of at least 8,000 samples, two speech cases and one
regression case with any active extras, both profiles. Every score uses the full
original PCM16 reference at its original gain. Evaluation and additional
independent cohorts were untouched. These results do not cover multi-segment
budget scheduling, a perceptual objective or the whole corpus.

Complete caps are `floor(original_bytes * percent / 100)` at 100/95/90%.
They include the 22-byte header, complete stored final packet, Rice spectral
choice, extras markers and byte padding. Spectra, scale/lag/gain, mandatory base
pulses and header filters stay fixed in this optional-pulse stage. Changing
spectra requires new accounting and reconstruction outside it.

The evidence keeps four roles distinct:

- **Original incumbent:** the larger frozen strongest stream and rollback.
- **Amplitude control:** the preserved position/amplitude fitting heuristic.
  Its lower-cap output can regress against the original incumbent.
- **Raw exact-greedy alternative:** complete marginal removal rounds, freshly
  ranked after every accepted removal, with a 1,024-render bound. A cap miss
  remains a miss even when its achieved-size comparison is useful.
- **Bounded swap alternative:** the amplitude seed plus up to 128 renders in
  32-candidate batches. Each accepted swap preserves that amplitude control's
  PCM/PWM SSE and available STOI floors. It remains a raw alternative relative
  to the original incumbent unless the original floors and later admission pass.

All public rows retain full PCM/PWM metrics, actual bytes, caps, no-fit/limit
outcomes and explicit adoption flags. Original-incumbent metrics and original
four-floor flags are also present in the bounded/matched-size rows. Byte
feasibility and quality admissibility are separate. No automatic adoption is
recorded by this report.

## Original-cap results

| Cap | Amplitude fit | Exact-greedy fit | Bounded fit | Bounded PCM SSE better / equal / worse among fits |
| --- | ---: | ---: | ---: | --- |
| 100% | 6/6 | 6/6 | 6/6 | 0 / 6 / 0 |
| 95% | 4/6 | 2/6 | 4/6 | 1 / 3 / 0 |
| 90% | 1/6 | 0/6 | 1/6 | 0 / 1 / 0 |

Three exact-greedy searches at each lower cap reached the render limit. The
remaining misses exhausted removable extras for those fixed fields. This is
not evidence that a different spectrum/excitation trajectory cannot fit.
Several fitting amplitude controls remove all extras, so no same-count swap
exists; those rows remain unchanged rather than being dropped.

The strict 95%-cap improvement is `pilot-005`, profile 4, in the regression
cohort. It saves **0.954% PCM error energy against its same-cap amplitude
control**, at exactly **1,765 B** for both outputs. It does **not** improve on
the larger 1,858 B original incumbent:

| Role | Bytes | PCM SSE | PCM STOI | PWM SSE | PWM STOI |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original incumbent | 1,858 | 16,413,373,120 | 0.733549 | 16,581,106,456 | 0.724604 |
| 95%-cap amplitude control | 1,765 | 19,329,585,328 | 0.725852 | 19,389,847,832 | 0.715500 |
| Bounded swap | 1,765 | 19,145,172,132 | 0.725897 | 19,194,666,264 | 0.715765 |

The swapped output fails the original-incumbent quality floors. Its accepted
swap is relative to the smaller amplitude control; it is not a default quality
admission or a claim of audible improvement.

Both 1,765 B streams passed the separate complete-player admission at normal
and +100-cycle IRQ load: all 32,000 samples per image, exact PWM/EOF/ticks, zero
underruns/errors. Full Flash is 6,338 B normal / 6,346 B stressed, program Flash
4,573 / 4,581 B and static SRAM 756 B. The recipe uses final decoder `5c7e0592`,
explicit ASM, queue 256 / prefill 192, 16 MHz / 8 kHz in simavr. See the
[same-cap receipt](../v5-encoder-candidate-admission-2026-10-28/allocator-same-cap.json)
and its [shared source/runtime binding](../v5-encoder-candidate-admission-2026-10-28/perceptual-pilot.json),
committed in `30fbb443`. No physical board was measured; firmware admission
does not change the original-incumbent quality conclusion.

## Equal achieved size and search cost

At six previously fixed exact-greedy achieved-size points, the exact marginal
ordering gives three lower PCM SSE values, three equal values and no worse
values than amplitude fitting at the same bytes. Reductions are 2.157%, 5.340%
and 3.366%. Three of these points missed their requested 95/90% caps; the
secondary comparison never relabels them as fitting those caps.

At those same six sizes, the bounded policy with frozen amplitude-control
four-floor checks gives two lower PCM SSE values, four equal values and none
worse: reductions 0.804% and 0.691%. Original-incumbent metrics and admission
flags remain separate in both matched-size reports.

The exact-greedy pilot took 225.63 s wall time, including actual packing of
every trial. The bounded original-cap pilot took 8.45 s wall time / 8.31 s
Python-process CPU; its matched-size checks took 6.38 s wall time. These are
different protocols and render limits, not a controlled speedup claim. Process
CPU includes the in-process native decoder, NumPy/SciPy/Numba DSP and metrics;
compiler subprocess CPU is excluded. Wall time includes selected-output
validation. All selected outputs were checked against the
independent full model and both native common/v5-only PCM **and PWM** outputs.
Target real-time support still requires linked player images with active IRQ.

## Parameter histograms only

The tuning measurement covers 40 profile groups, 20 streams and 6,000 stored
parameter packets per profile. There are no unplayed stored packets in this
particular sample; separate tests cover their accounting. Stream boundaries
reset history and never create an artificial repeat.

| Parameter layer | Profile 4 bits | Profile 6 bits |
| --- | ---: | ---: |
| Current 15-bit tuples | 90,000 | 90,000 |
| Hypothetical tuple-repeat flag | 93,040 | 93,415 |
| Hypothetical independent field-repeat flags | 84,975 | 85,611 |

Tuple repeats are only 196/5,980 and 171/5,980 transitions, so that marker sketch
grows the parameter layer. Field repeats and small scale/gain deltas deserve
later study; signed delta histograms are retained in `parameter-histograms.json`.
The sketches include their repeat markers and unchanged absolute field widths,
but exclude new-format headers, decoder code and final byte padding. No delta
syntax was selected, no format was implemented and no full-Flash saving follows
from these parameter-layer counts.

## Checks and reproduction

Eight allocation test groups cover exact serialization, actual full-render
removal choices, coupled ranking reversal, prefix/tail behavior, hard caps,
bounded feasible retention, admissibility rejection and confirmation instability.
Three histogram groups cover deltas/markers, partial tails and stream resets.
An existing 80 ms synthetic test assumes a numeric STOI and errors on `None`;
this was observed before these edits. `short-stoi-test.json` characterizes the
insufficient-length sentinel and confirms that no production floor was relaxed.

The scripts in [`reproduction/`](reproduction/) are the measured launchers
adapted for argument-supplied paths and input/output protection. Algorithm
settings, selection and metric flow are preserved; the original launchers,
input/artifact fingerprints and exact private receipts stay ignored. Run from
the repository root with Python 3.12, the dependencies in `runtime.json`, the
native compiler on `PATH`, and tools/tests directories on `PYTHONPATH`. The
private baseline manifest and immutable files must be supplied locally.

```sh
python Codecs/LPX/research/v5-rate-allocation-2026-10-28/reproduction/allocation_pilot.py \
  "$LPX_MANIFEST" build/rate-study/exact
python Codecs/LPX/research/v5-rate-allocation-2026-10-28/reproduction/matched_size.py \
  "$LPX_MANIFEST" build/rate-study/exact
python Codecs/LPX/research/v5-rate-allocation-2026-10-28/reproduction/bounded_pilot.py \
  "$LPX_MANIFEST" build/rate-study/exact build/rate-study/bounded
python Codecs/LPX/research/v5-rate-allocation-2026-10-28/reproduction/bounded_matched.py \
  "$LPX_MANIFEST" build/rate-study/exact build/rate-study/bounded
```

The manifest schema is `lpx-v5-encoder-quality-study-v1`, with immutable whole
references, ordered segment bindings, split/cohort labels and complete caps.
Generated media, private receipts and all per-recording fingerprints stay under
ignored `build/`. The histogram API accepts those valid stream bytes directly;
its CLI also accepts local streams and produces an anonymous aggregate report.
Do not run research scripts with Python optimization flags: validation uses
assertions. No external upload is needed for reproduction.
