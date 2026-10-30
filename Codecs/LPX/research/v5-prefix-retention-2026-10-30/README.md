# Retain visited full-record choices across deeper local search

The audited V2 study exposed a correctness gap on a multi-reset recording:
deeper per-reset winners can concatenate to more than the whole byte ceiling.
The final three-chain decision then rolls back even though a shallower visited
whole chain already fitted and passed every full-reference gate.

This separate research package replays existing bytes at common local depths
0..4, retaining selected and raw views at each depth. It also retains the
original default's three complete choices and the actual screen budget winners
and raw fallbacks. It never varies depths independently between resets.
The [protocol](PROTOCOL.md) was committed before new replay outcomes.

Scope is the post-observation diagnostic on anonymous source ordinal42,
profiles4/6, five actual reset segments each. This is neither held-out evidence
nor a production change. The frozen core, original V1/V2 studies and fixed
75-chain player campaign remain unchanged.

`prefixes.py` has no decoder or search imports. Its public helpers are
`prefix_pool_ids(report, depth)`, `ranked_prefix_ids(report, depth)`,
`common_prefix_descriptors(record, depth, label)`, `retain_distinct(chains)`,
`choose_budget(rows, original_bytes, percent)` and
`assert_incumbents_retained(rows, decision, incumbent_ids)`.
Ties use score, actual bytes and stable discovery order. Ordered reset byte
tuples are deduplicated; equal concatenated bytes with different resets are
different choices. No-fit and raw tradeoffs remain explicit.

Eight pure contracts pass. The actual-saved-row contract checks both profiles
and all ten resets:20 prefix1 selected/raw byte comparisons match the actual
one-call screen, and20 final-prefix ranks match the saved default. These checks
perform no encoding, refinement or new whole-chain measurement.

The replay requires the full independent V2 PASS for118 phase rows, the exact
frozen auditor source, binding, runtime and markers. Every distinct whole chain
is freshly decoded through the independent model and both native PCM16/PWM
layouts and measured over the entire target. Prior whole metric rows are not
reused; exact duplicate role views are measured once. Source features may be
shared for the same exact target. Known audited whole metrics must reproduce
field-by-field. Every100/95/90 choice must retain any known admitted feasible
screen/default incumbent with no worse joint score or equal-score byte cost.

Run pure checks directly and actual checks with private inputs:

```text
python Codecs/LPX/research/v5-prefix-retention-2026-10-30/test_prefixes.py
python Codecs/LPX/research/v5-prefix-retention-2026-10-30/test_saved_rows.py --study COMPLETED_V2_STUDY --output build/prefix-retention/fresh-contract
python build/encoder-quality/run.py Codecs/LPX/research/v5-prefix-retention-2026-10-30/replay.py --source-root ACTIVE_V2_ROOT --study COMPLETED_V2_STUDY --audit FULL_AUDIT_PRIVATE_RECEIPT --auditor EXACT_AUDITOR_SOURCE --output build/prefix-retention/fresh-replay
```

All outputs must be fresh under this analysis worktree's ignored build folder.
Unexpected failures retain a private traceback and partial work counters;
console output contains numerical progress or exception class only. No new
fit/refinement API may run. Media, identities, paths and fingerprints remain
private. No replay result expands the ongoing player campaign or establishes
audibility, hardware support or production adoption.
