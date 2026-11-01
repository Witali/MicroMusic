# Frozen combined v5 study: joint paths, perceptual ranking and bounded swaps

Base source: `0415d791`. This campaign changes no decoder or frozen predecessor
source. It tests the three host-side ideas together against the completed
expanded legacy search, with genuine rate/Flash savings taking priority over
small proxy-only differences. Objective scores are not listening judgments.

The original baseline-v2 has 49 full speech references / 98 profile groups,
118 actual reset segments and 2,632,296 unique reference samples. The original
split is preserved: 40 tuning groups, 40 evaluation groups and 18 additional
groups. Two tuning groups are used for correctness/runtime smoke; their exact
cached results can be reused in the full run. No settings are retuned on
evaluation or additional groups. All finite no-fit results remain visible.

For every group, the accepted expanded100 chain is the new search seed. The
initial pools contain the original chain and every available old-expanded
100/95/90 selected and raw/tradeoff segment. All source files, references,
ordered reset geometry, complete outputs, metrics and actual serialized bytes
are independently checked. Frozen-seed weighting is computed over the complete
original reference with the expanded100 seed's actual reset traces; its error
history continues across every reset. Candidate LPC never changes the weights.

The fixed trajectory configuration is frames 2, adjacent window 2, beam 2,
spectral finalists 2, excitation finalist 1, excitation horizon 80, local
scalar-LPC screening horizon 640, full synthesis limit 128, lambda zero. The
capacity callback uses bounded `improve_extras`, at most 64 allocator renders
within that same full-synthesis limit, candidate batches 32 and no local metric
admissibility predicate. Feasible serialized callback results are retained if
a subsequent branch reconstruction exhausts the shared budget. Full-render,
local-screen, excitation, allocation, confirmation and serialization counts
remain distinct.

Candidate-generation room for a segment is the original complete-chain cap
minus the cheapest fixed old-pool completion of the other segments, clamped to
the existing bounded-file interface. All three original caps are attempted.
These are generation heuristics, not proportional admission budgets. Final
caps are always `floor(original_complete_chain_bytes * percent / 100)` with
percent 100/95/90, counting every header, tail, extras marker and padding bit.

Whole-chain selection uses the established complete-waveform assembler:
beam 32, maximum 4,096 objective evaluations and its explicit bounded metric
shortlist/frontier. Where an old accepted same-budget control exists, it is
the assembler rollback anchor. Otherwise the original chain is the anchor.
Manual historical complete-chain alternatives are also retained independently
of beam pruning. Every promoted result must pass original PCM/PWM SSE/STOI
floors and the accepted same-budget control's floors where one exists. A
failed-original-floor old tradeoff is listening/control evidence only; its
floors are reported separately and never authorize promotion. The oversized
expanded100 control's floors are not imposed at 95/90%.

Both SSE and frozen-seed perceptual ranking use identical settings and initial
pools. Modes have separate candidate pools and caches. Every new stream and
final whole chain is checked through common/v5-only native C, independent
clipped integer synthesis and full PWM. No level fitting or trimming occurs.
All old accepted rollbacks remain eligible; acceptance failures cannot silently
overwrite a stronger control. Missing conservative fits remain null, not zero
error. This finite search and metric shortlist do not prove an optimum or
impossibility of a smaller codec stream.

The runner records source/runtime/input epochs, wall/process CPU time and
strict output hashes for resumable per-record caches. Prepared native libraries
are shared read-only; worker outputs and temporary files are separate. Old
campaigns remain immutable. Private paths, recording/stream/PCM fingerprints,
compressed audio and generated firmware stay in ignored build storage. Public
results contain anonymous numeric/source-bound evidence only.

Use the project Python environment with the three numeric-library thread counts
set to one. Prepare native libraries once, then run SSE/perceptual workers:

```text
python reproduction/run_combined.py --output build/combined-v1 --prepare-native
python reproduction/run_combined.py --manifest BASELINE_V2 --expanded TUNING_EXPANDED EVALUATION_EXPANDED ADDITIONAL_EXPANDED --output build/combined-v1 --mode sse --shard 0 --shards 2
```

Repeat shards 0/1 for both modes. The tuning smoke adds `--split tuning
--limit 2 --label smoke-sse` (or perceptual); source/settings/input cache keys
are identical to the corresponding full-run records. Compare strict rate
fits first, then complete original/control metric changes and measured encoder
cost. Full AVR Flash and active-IRQ admission of new winners is a subsequent
requirement; unchanged MCU source does not itself establish those results.
