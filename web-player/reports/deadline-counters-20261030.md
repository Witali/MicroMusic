# Deadline source counters, 2026-10-30

The optional diagnostic producer now distinguishes deadline-cache hits/misses,
invalidation causes, zero elapsed spans and conversions inside/outside the
scanner. It instruments only ignored native copies. Production libraries,
native artifacts and compiler identity remain unchanged from `9505a664`.
**No elapsed-time or speedup claim is made.**

Nine deadline-counter workloads and seven default-counter controls all match
uninstrumented production PCM, complete recorded public/diagnostic state,
memory, Flash, EEPROM, IRQ frames and retained tail-pin data. This is final
snapshot/tail parity, not complete pin-waveform or audio-underrun admission.
All **490 common source-entry counts** and output hashes match across the seven
paired control workloads. Arithmetic partitions and scanner entry/exit balance
are checked in the producer and the independent retained-data auditor.
Four local corruption checks also reject changed counts, native hash, duplicate
metadata and mismatched control counts.

Native production remains 124614 bytes, SHA-256
`b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`;
compiler identity is
`d67d0e37d909695ee35f8a90059d825f68008e42ec1ac231302c7f0bf51fa46b`.
The counted builds have no host imports. Counts include inlined C entries and
are not machine-call counts, source-line timings or percentages of elapsed time.

## Observations

Music uses 12000 frames at 48 kHz, physical/resumable nominal clocks and fast
idle with the existing ordinary block policy. These are not the conservative
verification preset or the bounded-region policy of the preceding long sampled
capture. External kernels use 1200 frames, periodic 20 MHz CLKI at /1 or /256;
the /1 ADC controls cover enabled-idle and converting states. Two new internal
20 MHz /1 kernels run one million instructions, with ADC disabled/converting.
No physical chip/calibration data or official simulator session is involved.

| Workload | Queries | Hits | Scans | `duration` inside scan | Outside scan | Zero spans with cached future |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rhythmic physical | 6380683 | 4160726 | 2219957 | 2305783 | 1504380 | 575983 |
| Lumière stereo physical | 6390073 | 4154100 | 2235973 | 2378416 | 1510645 | 566405 |
| HQ4 physical | 6670132 | 4384873 | 2285259 | 2369143 | 1517063 | 675375 |
| CLKI /1 | 3602404 | 2301601 | 1300803 | 0 | 0 | 300002 |
| CLKI /256 | 3004748 | 2002773 | 1001975 | 0 | 0 | 1174 |
| CLKI /1, ADC idle | 3602404 | 2301601 | 1300803 | 0 | 0 | 300002 |
| CLKI /1, ADC converting | 3602404 | 2301601 | 1300803 | 0 | 0 | 300002 |
| Internal direct | 1500009 | 1000006 | 500003 | 0 | 500001 | 2 |
| Internal direct, ADC converting | 1679685 | 1117186 | 562499 | 562499 | 523437 | 35156 |

Every observed zero elapsed span has a valid same-base cache with a future
deadline. This is an investigation candidate, not proof that servicing is
redundant. ELAPSE clears a valid cache at every observed call; SERVICE then sees
an already invalid cache. Both appear in the following miss's overlapping
reason set and must not be counted as two misses. Music additionally has read,
write, IRQ-ack and LPM causes; their full counts remain in the JSON.

The plain internal kernel performs **zero** duration conversions inside the
scanner: all 500001 conversions come from outside it. With converting ADC,
562499 are inside and 523437 outside. This corrects any inference that sampled
`at_half` source positions alone identify scanner conversion cost. CLKI performs
no Hz-based duration conversion in these cases, retaining its actual-edge path.

Next, isolate zero-duration arithmetic inside `elapse`, retaining invalidation,
service, wake/publication and fault behavior. Validate every phase/tie and use
balanced uninstrumented performance controls before retaining a change. Do not
skip service or revive rejected timer-budget/ADC guards from these counts.

## Evidence and replay

[Deadline data](deadline-counters-20261030.json) and
[default-counter data](deadline-counters-control-20261030.json) are the exact
completed producer summaries. Both pin original native/source/catalog and
counted-runtime hashes, function metadata, all counts and bounded virtual-time
prefixes. Ignored originals are under `build/traces/deadline-final-20261030/`
and `build/traces/deadline-default-final-20261030/`. Raw counted binaries and C
copies are not shipped.

```text
node web-player/scripts/verify-deadline-counters.mjs --input web-player/reports/deadline-counters-20261030.json --control web-player/reports/deadline-counters-control-20261030.json
```

See the [counter contract and full reproduction](../../docs/avr-asm-cookbook/deadline-source-counters.md).
The last 2659 runtime/shared checks apply to unchanged production; no broad
runtime rerun was needed for this diagnostic-only change. Exclusive subsystem
time, hardware ambiguities and full stage 5 remain open. The plan stays
**24/31 complete, seven open**. No download or system installation occurred.
