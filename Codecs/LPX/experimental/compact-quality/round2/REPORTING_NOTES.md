# Pilot reporting correction before reserve measurements

The one-case development pilot was measured with runner SHA256
`adf25ecb8f9c50259f47e50591e095650716788d87a9d8db69acc0e77a1f911c`.
Its public JSON and complete media/journal remain immutable. The original
reporting helper computed available STOI means independently for each variant,
which could produce different denominators when a score is missing.

Before any reserve source was encoded, the reporting helper was corrected to
use disabled-baseline per-case/path eligibility for all variants. Missing an
eligible score makes that mean unavailable and records the missing count.
Cases, bytes and waveform errors always retain every input. Independent
synthetic missing-value checks passed. The final runner SHA256 is
`8d4abc9be879f8beca8c12ad5ad7432e01b9a99197afce0179639e74ad50684f`.

No encoder, selector, candidate, loss, threshold, input, compiler command or
native binary changed. Renewed build receipts explicitly record this
report-only orchestration update and verify identical C++ inputs and binary
hashes. The original runner/receipts are retained in ignored local provenance.
The final matrix reuses the same immutable pilot artifacts and reports them
under the corrected aggregation rule. No pilot search was repeated, and it
does not count as another independent sample.
