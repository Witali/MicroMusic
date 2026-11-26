# Independent P3 reachable-neighbor tests

This is a separate check of the operator in `P3_NEIGHBORS_PROTOCOL.md`, after the
canonical local-trace fix. It does not modify or rerun into the frozen original
regression receipts. `p3_neighbors.cpp` includes the existing independent native
oracle with its main renamed, plus the one selected production/override helper
implementation. No public API or production compilation unit is added.

The runner independently reconstructs the exact two-site patch from the pinned
corrected source, requires the pinned override hash, and rejects all other byte
changes. The non-P3 enumeration order must remain -1,+1. Separate reference and
variant executables use identical production source lists/options and preserve
source/header/table and executable fingerprints in ignored
`build/compact-quality/p3-neighbor-independent/receipt.json`.

Tests cover legal single-field raw distances2/4 composing into distinct bundles;
rejection of distances1/3, unordered spectra, multiple fields, partial/non-boundary
runs, invalid scores, unrelated header/context/history changes, illegal pulses,
unplayed tails and cap violations. Composer eligibility is tested with supplied
scores; this does not establish whole-output quality admission.

The generator's spectral-trial count must equal an independently enumerated
legal four-delta neighborhood, with the registered bounds and deterministic
native-verified proposals. New-distance canonical no-ops, propagated holds and
local forward audio are checked against complete serialized native output,
including an actual1280sample prefix and carried-state suffix. Rates8/12/16kHz
and PCM/PWM targets are covered. Non-P3 complete proposal/counter fingerprints
must equal the fixed reference; the frozen882-case P4/P6/P8 native crop checks
also execute in these separate binaries.

```powershell
$env:LPX_TEST_WSL='Ubuntu'
python Codecs/LPX/experimental/compact-quality/tests/test_p3_neighbors.py
```

The generated override must already exist at its registered path. This test does
not generate it, launch speech/corpus searches, change quality gates, demonstrate
audibility or establish AVR timing/support.
