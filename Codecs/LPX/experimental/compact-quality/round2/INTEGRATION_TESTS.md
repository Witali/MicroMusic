# Independent P3 integration gate

The separate `tests/test_integration.py` gate passed **4/4** in 50.946 seconds
on 2026-11-26. It builds and runs the current portable decoder/host sources with
GCC 13.3.0 under WSL Ubuntu, `-O2 -std=c++11 -ffp-contract=off`, the project's
`portableDefines`, and explicit `LPX_ENCODER_COMPACT_ENSEMBLE=1` and `=0`.
The existing first-study tests and receipts were left unchanged.

Frozen production inputs:

| File | SHA-256 |
| --- | --- |
| `host/LpxAccuracy.cpp` | `a7206f9e34c62f35fbf89c54d135bbd59b699abb9de2670271686bd909d7d91c` |
| `host/LpxAccuracy.h` | `1d20e25688aa42c74afeff70bf9d2798e312ec33143882e0827e62c7a7b8abfa` |
| `host/LpxAdaptiveController.h` | `ffcdc8533e31bc4c19fbdfbaa0d041b823294ddfbc6c741af9ffec30a30ee38d` |

Coverage:

- 30 reset/partial-tail cases verify physical P3-to-fine relabel identity and
  actual native PCM/PWM/EOF. Odd-rank packets retain their fine grid; forcing
  them back to P3 demonstrably changes packed bytes and, with sufficient real
  samples, PCM.
- 60 eligibility checks cover both quality targets, calls0..3 and invalid counts,
  nonnull reset/continuation prefixes, 12/16 kHz, other accuracy levels, P6,
  nonzero synthesis/ring/filter state, lookahead, invalid target, and the
  1/64000/64001 sample boundaries.
- 70 rollback/cache/guard cases per build verify search errors, invalid geometry/policies/native
  pulse symbols, brightness activation, actual B0 growth, foreign target and
  source caches, wrong reference length, stale capture and capture aliasing.
  A genuine odd-rank candidate is accepted on each target by the unchanged
  `selectQualityProposals`, and stays at host accuracy4 through native replay.
  A nonexact candidate cannot displace an exact finished floor.
- 26 complete synthetic encode/C API/alias cases per build run calls0..3, P4/P6/P8,
  12/16 kHz and a nonnull reset prefix. Twenty excluded output/native-PCM and
  explicit legacy-counter fingerprints agree across switches. The eligible
  enabled case reports exactly one additional search. The C API's final pack
  matches the returned host stream on both PCM and PWM targets.

Reproduce from the repository worktree in PowerShell using an installed WSL
Ubuntu/GCC and Python:

```powershell
$env:LPX_TEST_WSL='Ubuntu'
python Codecs/LPX/experimental/compact-quality/round2/tests/test_integration.py
```

The ignored receipt at
`build/compact-quality/round2-integration-independent/receipt.json` retains the
full compiler commands, all input and binary hashes, per-build assertions and
`passed:true`. The runner refuses changed inputs during compilation.

This is synthetic reset-file integration evidence. It does not run speech,
establish continuation support, replace the eight development baseline checks,
execute WASM, measure AVR timing, or demonstrate audible improvement. Geometry
boundaries are tested directly rather than performing a 64001-sample search.
The malformed-native cases are rejected before decode; no artificial decoder
fault injection or search-exception hook is used.
