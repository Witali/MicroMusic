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

## Corrected packet boundary

v5 stores complete 320-sample packets even when the requested output ends
inside a packet. The decoder now checks trailing bytes and nonzero pad bits
only after both the half and subframe indices return to the full-packet
boundary. Merely being in the second half does not establish that boundary.
Unread fields in a partial final packet remain permitted by the native
streaming contract; the strict host unpacker still validates the whole packet.

The historical table above is retained unchanged. Regression coverage checks
every output offset in the first two packets, both spectrum profiles, common
and v5-only layouts. The formerly failing aligned tails also run with the
reference counter/reader/history settings, snapshot copies, LPC segments
1/2/4 and bandwidth expansion. Complete-packet trailing bytes and nonzero
padding remain rejected. This is a correctness fix, not a size optimization.
