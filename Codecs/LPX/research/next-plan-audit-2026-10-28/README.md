# Source-audit tail probe

This synthetic probe characterizes current main `5b7ae1a6`; it is not an
optimization benchmark and changes no decoder source. Existing `fixture()`
constructs v4 fields, `repack()` creates complete v5 packets, and `decode_model()`
strictly validates them. Common and v5-only native decoders are then compared
for the declared sample count. The table records acceptance, not an asserted
native error-code classification.

Run from the repository root with active tools/tests on PYTHONPATH, the existing
Python dependencies and a native g++:

```text
python Codecs/LPX/research/next-plan-audit-2026-10-28/tail_probe.py
```

The 28 observed results are retained in [tail-results.json](tail-results.json).
Both native layouts reject N=180/200/220/240/260/280/500 for both profiles,
while the strict model accepts each complete stream. They accept the seven
control lengths. The end-of-output predicate at core line1013 also runs on
20-aligned second-half tails. Format semantics and a separate corrective patch
must be settled before changing phase/count representations; do not refresh
oracles merely to hide a disagreement. No source audio, private paths or
recording fingerprints are involved.
