# Independent Long policy gate

The new `tests/test_long.py` gate passed **6/6 groups** in 604.233 seconds on
2026-11-26. It uses synthetic inputs only. Earlier short-study tests, sources
and receipts remain unchanged.

Four builds pair the exact pre-extension source with the extension, each with
explicit `LPX_ENCODER_COMPACT_ENSEMBLE=0` and `=1`. All other host/decoder objects
are shared: only `LpxAccuracy.cpp` and its header use this feature macro. GCC
13.3.0 under WSL Ubuntu uses `-O2 -std=c++11 -ffp-contract=off` and the project's
portable decoder defines, including the existing wide-V9 entry point.

| Input | SHA-256 |
| --- | --- |
| Previous `LpxAccuracy.cpp` | `a7206f9e34c62f35fbf89c54d135bbd59b699abb9de2670271686bd909d7d91c` |
| Previous `LpxAccuracy.h` | `1d20e25688aa42c74afeff70bf9d2798e312ec33143882e0827e62c7a7b8abfa` |
| Extended `LpxAccuracy.cpp` | `858489709bf077718ffb35a676ff7d4b99ab5a9905097ae54e154bea64fc7340` |
| Extended `LpxAccuracy.h` | `a50478c45d40539f276be84dd2fe80999b0cbebb1cdfdb55f2ae5c5dda27d2dc` |

Coverage:

- 18 continuous native PCM/PWM/model/EOF cases cover 64000/64001,
  65535/65536, 128001, 159999, 160000/160001 samples, enhanced syntax and a
  separate 1,600,000-sample stress stream with more than 65,535 payload bytes.
  Header flag/length, actual little-endian sample/payload high words and
  produced counters are checked. Five malformed header/length cases reject
  and permit valid reset/restart afterwards. The large stress stream is
  deliberately outside optional-search scope.
- Each paired build performs 64 checks of the old or new exact sample boundary and unchanged
  exclusions: other rates/levels/profiles/call counts, nonnull reset and
  continuation prefixes, nonzero state/lookahead and invalid target. Above-limit
  refinement keeps the exact completed stream without searching or stale capture.
- Six genuine Long odd-rank candidates pass the unchanged complete selector
  and remain at host accuracy4. Twenty-four rollback cases preserve the floor
  for explicit search errors, actual complete-B0 growth, malformed data and
  mismatched target context. B0 includes the existing 17-byte Long header.
- Eight complete short/Long host and C API encodes per paired build prove macro0 predecessor byte and
  legacy-counter identity, and enabled short-input compatibility.
- Two real nonzero multi-window streams per enabled/disabled build preserve
  carried state, native continuous output and terminal EOF. Their complete
  serialized fingerprints match across switches; the optional phase remains
  outside streaming scope.
- Four nonzero short/Long composition cases per paired build use both quality
  targets. A fresh nonnull reset-prefix floor is identical across builds and
  to the macro0 null-prefix floor in **all host model fields**, bytes, PCM and
  every legacy report field. Direct refinement of that retained floor equals
  the ordinary automatic result. The baseline/context remains immutable.

Composition retains nominal policy C from the baseline report separately.
Direct `refineCompactEnsemble` resets its own optional report and does not set
the caller's C field; this is expected. Both paths use actual `packV9(floor)`
as B0, and leave preceding report fields unchanged.

Reproduce using installed Python and WSL Ubuntu/GCC, after retaining the pinned
previous source/header under the ignored `pre-long/` directory:

```powershell
$env:LPX_TEST_WSL='Ubuntu'
python Codecs/LPX/experimental/compact-quality/audiobook-study/tests/test_long.py
```

The ignored receipt is
`build/compact-quality/audiobook-study/independent/receipt.json`. It contains
the six group results, all source/header/protocol/test hashes, compiler commands
and four binary hashes. Compilation refuses changing inputs. The prior helper
tests are reused without modification; no audiobook data enters this gate.

This establishes host policy/container/native decoder equivalence. It does
not establish audible quality, actual WASM execution, AVR Flash/SRAM admission,
interrupt timing or physical-board support. No decoder source was changed.
