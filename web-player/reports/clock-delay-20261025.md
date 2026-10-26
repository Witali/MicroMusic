# Rejected native-width clock-delay simplification

Rejected and removed from production. The candidate subtracts retained phase
before division when `units * denominator` fits uint64, reducing repeated
quotient/remainder work. For validated nonzero units and phase<denominator,
subtraction cannot underflow; ceil(n/rate)<=n prevents increment overflow.
Large products retain the original wide algorithm and its failure admission.
No native event, source phase, timestamp unit or MCU register changes.

All1674 candidate tests pass. The additional BigInt/WASM check covers67692
fraction/product-boundary combinations, including original wide-intermediate
overflow rejection and unchanged output on failure. The13-case untimed parity
mode retains26 runs/168 snapshots (84 cross-checks): exact PCM, full CPU/device
state and pins, including CLKI/divisor/active-ADC controls. The runner now offers
`--validate-only` so correctness matrices need not imply timing evidence.

The candidate runtime is117951 bytes, SHA-256
`dc2c069206ee8079b7d5a0ddd46f5c3beb2f80319acd6f01fc019d001c934c9f`.
It preserves no-host-imports,109 function exports and fixed two-page memory.
An isolated build reproduces every byte. Exact optimized-function comparison
finds202 unchanged bodies and one changed body: `duration`,526→576 bytes.
This static change is not proof of runtime improvement.

Windows/Ryzen5600X, Node22.22.3, pinned Clang24/Binaryen133 SDK6.0.12; one
unchanged generated CPU per workload. Eight balanced four-label trials and four
warmups per label preserve native Module sharing within identity pairs, fresh
CPU modules/instances, equal inputs and complete per-block comparisons. No
concurrent test/profiling work runs during timing.96 timed runs and48 warmups
retain1728 snapshots (1692 comparisons against first reference snapshots).

| Case | Old identity median | New identity median | Old/new median | Paired range |
| --- | ---: | ---: | ---: | ---: |
| rhythmic compatible | 1.008x | 0.998x | 1.004x | 0.978–1.040 |
| rhythmic physical | 0.989x | 0.973x | 1.002x | 0.858–1.059 |
| HQ4 physical | 0.992x | 0.962x | 0.993x | 0.548–1.171 |

No speed gain is established. The remaining timed cases are not run; all13
already passed the separate correctness matrix. Candidate sources/binary,
manifest, timing records, function analysis/diff and full TAP are retained in
[clock-delay-20261025/](clock-delay-20261025/). Baseline is `410be01`.
The original header, runtime and manifest are restored; production remains
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.
All five focused clock tests pass after restoration; the new regression remains.
No browser/cold-start/working-memory/audio-underrun improvement is claimed.

```sh
node web-player/reports/clock-delay-20261025/verify-evidence.mjs
node web-player/reports/clock-delay-20261025/rebuild-candidate.mjs
```

Next test exact reduction of the physical picosecond→nanosecond fraction in its
own clock domain. A private reduced remainder can avoid repeatedly multiplying
and dividing by1e9; NVM deadlines must convert it back to their numerator units.
Keep legacy clocks, large timestamps, event/IRQ/reset ties and general ratios
unchanged, then repeat the full parity and identical-runtime gates. This is a
separate unimplemented candidate. The full-device plan stays21/30.
