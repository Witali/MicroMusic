# Distinct P3 reachable-neighbor experiment

Registered on 2026-11-26 after the isolated canonical-score correction completed
with byte-identical outputs in all eight public speech cases. That result and
its frozen harness remain unchanged. This is a separate operator, not a quality
gain attributed to the eight-line predictor-fidelity correction.

## Mechanism and exact changes

P3 quantizes the ordered LSF rank residual to an even grid and reuses a previous
vector when its maximum bin distance is at most two. Raw ±1 neighbors are
asymmetric: a negative step commonly rounds away, while a positive step can
become +2; even ±2 can be held. The next natural one-field distances are ±2
(grid spacing) and ±4 (the first spacing beyond the two-bin dead zone relative
to an equal previous vector). Neither distance guarantees an effective change
for an arbitrary prior vector; full canonicalization is authoritative.

Generate an experimental override from the exact corrected source SHA-256
`cba09bfaab7092612befeab2e2f5af9304787ad7131efa88740bcb58abb1f8a7`.
Apply only these two checked, P3-specific changes:

1. `proposeLpcRuns` enumerates deltas `{-4,-2,2,4}` for accuracy3; all other
   profiles retain `{-1,1}`. Existing legality and actual byte-cap checks apply.
2. `composeLpcRuns` recognizes one changed raw field of magnitude2 or4 for
   accuracy3; other profiles retain magnitude1. Preserve all remaining run,
   context, metadata, legality, prefix and whole-output checks.

The composer adjustment is part of this explicit operator: changing only the
generator would reject every new single from composition and silently change
the experiment's scope. Existing code must still evaluate all original single
proposals as well as eligible bundles; no additive quality assumption is made.
Canonical holding can affect later transmitted frames beyond the raw edited
run, so complete packed/native output remains the acceptance authority.

Do not change source preprocessing, losses, tie ordering, run count4, local
horizon1280, shortlist2, pulse-adaptation span160, header/pitch/scale search,
quality weights or acceptance criteria. The new neighborhood has at most40
raw field/delta trials per run, versus20 before legality/cap/dedup filtering.
This is additional encoding-host work; the decoder and wire syntax are fixed.

## Controls and admission

Keep production source and the frozen original/fixed binaries, benchmark.cpp,
compare.py and their reports unchanged. A separate runner may create a pinned
generated CPP under ignored build storage and compile a third executable using
the same source list and options. Record the exact checked patch, source and
binary hashes and compiler. Refuse an unexpected source or patch count.

First verify the new generator/composer contracts independently, including
accepted legal ±2/±4 P3 single-field edits, rejected illegal/multi-field/context
changes, raw canonical no-ops, full dead-zone propagation, unchanged P4/P6/P8
semantics, exact native output and real continuation. Do not infer correctness
merely from compilation or the previous canonical-helper test receipt.

Use the same four public sources, P3/8k/calls4 and PCM/PWM targets as phase1.
Pilot chego in both targets, then the fixed eight-case matrix. Freeze all
changes before pilot outcomes, with no tuning on those outcomes. Compare with
the stored exact original complete baseline per case; the phase1 corrected
output is the same bytes. Re-verify its source, stream and PCM hashes.

Report the raw new encoder result and a separately labelled protected output.
The protected output uses phase1's explicit additional strict floors and
actual-byte ceiling B0. The nominal policy allocation C is reported separately.
Any growth versus B0 remains growth, even if it fits P3's allocation. Retain
raw rejected outputs and all measured changes. No extra correction flag,
decoder table, rounding rule, payload field or sample-rate change is allowed.

For host timing, report actual new execution time. If the original timing is
reused from phase1 rather than measured in a paired concurrent-load context,
label it as a prior-run reference rather than a controlled speed ratio.

This mechanism is a P3 quantizer-aware proposal extension. Numerical or audible
benefits remain unestablished until this separate comparison. No new general
speech, AVR real-time or physical-board support claim follows from this plan.
