# Joint spectral/excitation rate pilot

[PROTOCOL.md](PROTOCOL.md) fixes the finite search, whole-record byte budget,
quality gates and five controls. [PREFLIGHT.md](PREFLIGHT.md) fixes warmup and
the separately bound old-native/new-model bridge. [RESULTS.md](RESULTS.md)
reports the completed pilot and its limits. Public evidence is anonymous numeric
data; private bindings, media, exact byte identities and logs remain ignored.

Production source is frozen at b21cb028bdb2ae3c285fbc2d9ccac96ca3c447d0. Invoke the
research scripts with the explicit frozen production worktree; the integrated
latest tools are not a replacement for that numerical epoch. Use the project's
Python/dependency/thread/compiler bootstrap. No source may change during workers.
Every output directory must be fresh under the research worktree's ignored build.

1. Run `prepare_baselines.py` with the closed matched-CPU study, original V2
   study, positive ROM/SPI handoffs and final complete proofs. Its source root
   and source commit identify the preparation epoch. This reconstructs targets
   and chooses the strongest 104 baselines without fitting, decoding or metrics.
2. Run `python -m unittest discover -s <research-package> -p "test_*.py"`.
   Set `JOINT_RATE_BASELINES`, `JOINT_RATE_SOURCE` and `JOINT_RATE_NATIVE_CASES`
   to enable the actual saved-manifest/native-closure contract as well as pure
   tests. Contract failures do not justify changing pilot settings.
3. Run the ten-helper synthetic preflight. After PASS, run exactly one profile 4
   and one profile 6 shard, with the same baseline and native case manifests:

```text
python run_pilot.py --source-root <frozen-b21-worktree> --source-commit b21cb028bdb2ae3c285fbc2d9ccac96ca3c447d0 --baselines <prepared-binding> --native-cases <closed-cases-private.json> --output build/joint-rate/preflight-v1 --preflight-only
python run_pilot.py --source-root <frozen-b21-worktree> --source-commit b21cb028bdb2ae3c285fbc2d9ccac96ca3c447d0 --baselines <prepared-binding> --native-cases <closed-cases-private.json> --output build/joint-rate/pilot-v1-p4 --profile 4
python run_pilot.py --source-root <frozen-b21-worktree> --source-commit b21cb028bdb2ae3c285fbc2d9ccac96ca3c447d0 --baselines <prepared-binding> --native-cases <closed-cases-private.json> --output build/joint-rate/pilot-v1-p6 --profile 6
```

4. Preserve every attempt and terminal receipt. Do not restart an interrupted
   helper or substitute its work without explicit coordination. After both
   terminal source/input guards pass, run `project_pilot.py --baselines
   <prepared-binding> --preflight <preflight-output> --shards <profile 4-output>
   <profile 6-output> --output build/joint-rate/export-v1`. This reconstructs
   saved recipes/choices/cache provenance and performs no codec execution.
5. Optional post-pilot description is `diagnose_pilot.py --study build/joint-rate
   --output build/joint-rate/diagnostics-v2`. It uses only saved numeric metrics
   and reports branch reach, magnitudes and gate failures. The original
   diagnostics-v1 is preserved; v2 adds saved pitch-proxy differences, with no
   new fits, decoding, metrics or altered decisions.

The actual preflight session 22160 and corpus sessions 89817/93354 exited 0.
Projector 99506 and saved-only diagnostic 8047 exited 0. Private result paths use
the output names above. The root owns any decision to broaden the study or
request finite target images. No full-corpus or target-image launch follows
automatically from a numerical pilot result.
