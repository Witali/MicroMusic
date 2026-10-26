# Bounded-multiplier clock arithmetic experiment

Rejected against `bb5f329`. For two 32-bit multiplicands the product fits in
64 bits; the candidate checks the subsequent carry addition with `sum>=carry`
instead of dividing to check multiplication overflow. Larger operands retain
the original wide fallback. No AVR clock edge or peripheral event is omitted.

All 1634 Node checks passed, including 864 BigInt-oracle combinations around
32-bit bounds, 64-bit addition wrap, zero divisors and result overflow.
The isolated rebuild reproduces candidate SHA-256
`dfca64f8abdbc7c9fd22eff41cd6d963f7299128c695c2fde32c723ed21dc1af`.
It is 117949 bytes, 48 bytes larger than production, with the same fixed
two-page memory, no host imports and 109 function exports.

| Screening case | Old identity | New identity | Cross ratio | Faster trials |
| --- | ---: | ---: | ---: | ---: |
| rhythmic-compatible | 1.000 | 0.997 | 0.945x | 0/8 |
| rhythmic-physical | 1.000 | 0.997 | 0.947x | 0/8 |

Ratios above one favor the candidate. The balanced four-label screen contains
64 timed runs, 32 discarded warmups and 1128 exact PCM/state/pin checkpoints.
Both cases regress with stable identity controls, so the remaining acceptance
matrix was not run. `complete:true` in the raw report refers only to this
two-case screen. These are Node/V8 measurements, not browser guarantees.

Exact named-build comparison finds 201 byte-identical function bodies and two
changed bodies: `duration` grows from 526 to 543 bytes and `ratio` from 464 to
495 bytes. Static opcode counts do not explain dynamic timing on their own.
The C header and production binary/manifest were restored; seven focused checks
pass after restoration. Production remains SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.

[Archived sources, raw measurements and analysis](clock-multiply-20261024/analysis.json)
include the harness, full test output, candidate binary and function WAT diffs.
Reproduce the candidate without modifying production:

```sh
node web-player/reports/clock-multiply-20261024/rebuild-candidate.mjs
```

Next inspect automatic optimization of the generated CPU module separately
from the already optimized C/WASM peripheral runtime. Preserve imported-memory
ABI, dispatch-table geometry, manifest, traps and every AVR observation boundary.
The full-device plan remains 21/30 complete; this rejected candidate closes no
additional hardware-support item.
