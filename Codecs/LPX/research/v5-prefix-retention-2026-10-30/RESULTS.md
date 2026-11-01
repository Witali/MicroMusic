# Prefix retention diagnostic: result

The replay passes. Retaining visited whole chains prevents the observed deeper
search rollback on profile6 without fitting or refining any new candidate.
This is a targeted correctness result, not a listening improvement claim.

| Anonymous source42 | Whole ceiling | Original default choice | Retained choice |
|---|---:|---|---|
| Profile4 | 16,142 B | control, score0.1951054005822384 | same control |
| Profile6 | 23,259 B | control, score0.13613320806467044 | actual screen/prefix1, score0.1361295932218511 |

The quality-admitted later common prefixes exceed the original caps. Profile4
has 19,316 B at depth2/3 and 19,669 B at depth4. Profile6 has 25,176 B at depth2/3
and 25,980 B at depth4 for selected views. Raw views remain separate. Neither
profile has an automatically admitted result at95% or90%; this finite replay
does not prove that another encoding could not fit those caps.

Thirty role views reduce to twelve distinct ordered-byte whole chains: five
for profile4 and seven for profile6. Every distinct chain was freshly decoded
and measured: sixty model reset calls, 3,379,584 modeled samples, 240 native
PCM/PWM domain comparisons, 48 full concatenation checks and twelve complete
metric rows. Repeated samples across chains are counted as work, not unique
source material. No old whole metric row was reused. The measured replay region
took49.32 s; this excludes development, contract tests and bootstrap recovery.

Eight pure contracts and the actual two-profile contract passed before replay:
twenty prefix1 selected/raw byte matches and twenty final-prefix rank matches.
Source/input guards and all six100/95/90 incumbent assertions pass. The full
independent V2 PASS118 and exact frozen source/runtime are bound privately.

Two bootstrap launches failed before the replay script could create an attempt:
the ignored launcher was initially absent, then its runpy wrapper lacked sibling
module resolution. Both logs and zero-native/zero-metric receipts remain private.
The one actual replay attempt completed. `run_replay.py` provides the sibling
bootstrap for a generic runtime wrapper without changing the executed replay.

From an analysis worktree with the pinned numerical runtime/compiler:

```text
python build/encoder-quality/run.py Codecs/LPX/research/v5-prefix-retention-2026-10-30/run_replay.py --source-root ACTIVE_V2_ROOT --study COMPLETED_V2_STUDY --audit FULL_AUDIT_PRIVATE_RECEIPT --auditor EXACT_AUDITOR_SOURCE --output build/prefix-retention/fresh-replay
```

The executed replay sources in `source-runtime.json` remain byte-identical to
the guarded run. Projection/bootstrap helpers were added afterward and perform
no search. `export_results.py` regenerates the allowlisted public JSON from the
immutable private replay, binding and pre-replay contract receipt.

The selected profile6 chain is already the actual screen selection retained in
the separately frozen 75-chain player union. No new selected chain is introduced,
and that campaign's scope is unchanged. This package does not edit production
or establish new hardware support, audible gains or general corpus improvement.
