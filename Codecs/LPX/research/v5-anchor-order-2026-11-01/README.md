# Separate anchor-ordering pilot

[PROTOCOL.md](PROTOCOL.md) fixes four lambda-zero/full-screen arms, identical
pre-pilot seeds and complete records, 80 fresh corpus helpers, 144 cap views and
separately paid 16 synthetic helpers. The earlier joint-rate pilot remains
immutable and supplies no free winners or candidate seeds to this experiment.

The exact production root HEAD is 55ebc0d94e919fa7aeec4819e3bf83cfaf81fa6a;
implementation ancestor 099d040afa2a2e77e1a15e3082de20c585a46929 has identical
production tools/tests/src. Every production import is explicitly checked against
the declared source root. The research checkout's older codec files must not be
silently loaded. The native libraries retain their old callback-enabled recipe
and epoch; the exact closure/receipt/binary bridge is shared with the immutable
[earlier runtime](../v5-joint-rate-2026-11-01/pilot_runtime.py), including its
documented historical build-JSON indexing limitation.

Use the project dependency/bootstrap environment with one numerical thread:

```text
python prepare_anchor.py --original-binding <original-pre-pilot-binding> --output build/anchor-order/baselines-v1
python -m unittest discover -s <anchor-research-package> -p "test_*.py"
python run_anchor.py --source-root <frozen-priority-worktree> --source-commit 55ebc0d94e919fa7aeec4819e3bf83cfaf81fa6a --baselines <anchor-binding> --native-cases <closed-native-cases> --output build/anchor-order/preflight-v1 --preflight-only
python run_anchor.py --source-root <frozen-priority-worktree> --source-commit 55ebc0d94e919fa7aeec4819e3bf83cfaf81fa6a --baselines <anchor-binding> --native-cases <closed-native-cases> --preflight build/anchor-order/preflight-v1 --output build/anchor-order/pilot-v1-p4 --profile 4
python run_anchor.py --source-root <frozen-priority-worktree> --source-commit 55ebc0d94e919fa7aeec4819e3bf83cfaf81fa6a --baselines <anchor-binding> --native-cases <closed-native-cases> --preflight build/anchor-order/preflight-v1 --output build/anchor-order/pilot-v1-p6 --profile 6
```

Set ANCHOR_BASELINES, ANCHOR_SOURCE and ANCHOR_NATIVE_CASES to enable the actual
saved-input scope/source/native contract. Every output directory must be fresh
under this research worktree's ignored build. Freeze source before preflight;
corpus shards require its completed same-source receipt. Do not change source
or start replacement work while either worker is live. Journal synthetic and
corpus attempts separately; a poll timeout is not permission to restart.

The harness shares immutable V1 whole-audit, native bridge, exact local frontier
and five-recipe operators. Its local/arm execution is an isolated adaptation of
the earlier driver, with new fixed arm mapping, additive counter contracts and
independently timed plan-order reconstruction. No V1 source is edited. Pair
postchecks require the same nominated set for time/priority at all 40 paired
reset contexts. Numerical quality, actual stored bytes, paid branch reach and
full workflow cost remain separate from target Flash/playback and listening.
