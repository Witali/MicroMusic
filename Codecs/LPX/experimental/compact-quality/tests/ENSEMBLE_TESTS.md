# Existing-encoder ensemble validity gate

This separate synthetic gate validates the frozen adapter in
`P3_ENSEMBLE_PROTOCOL.md` before any speech encode. It includes
`benchmark_ensemble.cpp` with `LPX_ENSEMBLE_NO_MAIN`, adds no production API, and
uses the actual portable native receiver for PCM/PWM and complete EOF checks.
It does not change the original local-trace or neighbor tests or their receipts.

The source is pinned to SHA-256
`93ad5a02dacdb91f643dde70b26270df3d73d405d3bc88a9dfa86424ce426a81`.
GCC13.3.0, production portable defines/source list, `-O2 -std=c++11
-ffp-contract=off`: four groups passed on2026-11-26 in31.382s.

| Contract | Cases |
| --- | ---: |
| P3→host accuracy4 identity, every physical field/byte and native PCM/PWM/EOF | 30 |
| Legal odd-rank fine packets retained; wrongly forced P3 demonstrably alters output | 10 |
| Strict B0 growth, target/policy, malformed geometry and active-SSE rejection | 50 |
| Forced search error, malformed/growing result fallback and preserved valid raw result | 28 |

Both PCM and PWM target policies are exercised. Strict old-noise rejection bits
are also checked against independent active-path measurements. Invalid brightness
is checked against the existing decoder maximum11469; it must be rejected before
synthesis. The tests do not infer a stricter waveform-SSE/noise contract from the
production selector: the explicitly experimental wrapper supplies those floors.

The search-result test uses `settleSearch` to force errors without invoking an
encode. A syntactically valid regressing raw result remains available for quality
diagnostics; it is not silently replaced and called a search failure. Only the
separate `protect` step decides admission. Baseline relabels are physical copies,
and a no-change result remains a no-change result.

```powershell
$env:LPX_TEST_WSL='Ubuntu'
python Codecs/LPX/experimental/compact-quality/tests/test_ensemble.py
```

The gate receipt is ignored
`build/compact-quality/p3-ensemble-independent/receipt.json`, including
`passed:true`, the adapter hash, exact compiler command and linked source,
header/table and executable fingerprints. The third-arm runner verifies that
receipt before speech access. These are reset complete-file/partial-tail checks;
no continuation, sound-quality, timing or AVR support result is claimed.
