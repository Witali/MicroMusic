# Timer0-derived CPU deadline budget: rejected

The candidate avoids an inverse base-time-to-CPU conversion when the current
earliest board deadline is exactly the converted Timer0 event. It retains the
original scheduler, event ordering and strict admission bounds. The cache flag
and uint32 distance occupy existing padding in the 24-byte deadline record.
Its [arithmetic proof and constraints](../../docs/avr-asm-cookbook/timer-deadline-budget.md)
explain when that inverse conversion is redundant.

Baseline is `6cb27abb384591bbff37e2a6c1e8f1182acb1ea3`, native 118,969 bytes,
SHA-256 `9f1eefa094f9003419251408953309e3b3c4050fc217234b9b95ed0275d87778`.
Candidate is 119,158 bytes (+189), SHA-256
`a0db59e0ceac21295a2693f286fa675caf2443011d457d9a035e3ad4bcd7006a`.
Only `native/peripherals/device.c` changes among native build inputs; exports,
flags, source list, CPU ABI and fixed two-page linear memory agree. No host
callback or production instrumentation is added.

## Correctness and measurements

All **1888 candidate default/shared-tool tests passed**, zero skipped, in 87.48 s.
The 16 new focused cases compare the actual board conversion with the pinned
original C implementation and an independent BigInt expression. They cover
1 Hz..20 MHz, compatible/physical clocks, /1../256, retained odd/fractional phases,
queued input at exact and adjacent 1-ps Timer0 deadlines, ADC/watchdog/NVM/CLKPR
deadlines, synthetic overspeed/wide distances, CLKI zero admission and timestamp
overflow. The frozen candidate-specific test also verifies that the derived
budget is actually used for eligible synchronous events.

The timing screen is coupled native execution on Node 22.22.3 / V8 12.4, Windows
x64 Ryzen 5600X; Clang 24 / Binaryen 133. Three real firmwares use 12,000 frames;
three kernels use 1200 frames, at 48 kHz. Each case has four full warmups per
label, eight Williams trials with four labels, fresh instances/modules and
identical CPU bytes/options/ABI across labels. PCM, complete state/memory/IRQ and
tail pins match after every captured batch. Setup, snapshots and hashing are
outside timers. No project test/profiler/other benchmark ran alongside timing.

| Case | Old identity median | New identity median | Old/new median | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Rhythmic physical | 1.003 | 1.010 | 1.010x | 5/8 |
| Lumière stereo physical | 1.018 | 0.992 | 1.007x | 5/8 |
| HQ4 physical | 1.015 | 0.974 | 0.991x | 4/8 |
| CLKI 20 MHz /1 | 1.003 | 1.012 | 0.965x | 0/8 |
| Internal 20 MHz /1 | 1.007 | 0.996 | 1.057x | 8/8 |
| Internal 20 MHz /1, ADC active | 0.900 | 1.090 | 1.041x | 5/8 |

Total: **192 timings, 96 warmups, 2016 full snapshots, 1974 comparisons**.
Ratios above one favor the candidate. The apparent real-firmware gains do not
separate convincingly from null-control variation. CLKI is slower in every
pair (0.910..0.987x), despite the derived-budget path being disabled there.
The internal synthetic result is insufficient for acceptance; some identity
pairs vary substantially (the full ranges are retained). Code placement and
host JIT/tiering effects are not controlled, so no C-source cause is inferred.
This is one screening interval; no confirmation matrix or browser run was made
after the screen failed the acceptance gate.

## Decision and retained work

**Reject the extra cache.** Production C source, WASM and manifest are restored
exactly to baseline. The retained 16 boundary tests pass on that restored state.
Text identities normalize LF; the WASM comparison is byte-for-byte.
The benchmark accepts a descriptive `timer-deadline-budget` change-set label to
replay this archived candidate. No other default behavior changes.

The user-requested [model simplification plan](../native/MODEL_SIMPLIFICATION.md)
is saved separately: clear controller ownership, one event scheduler with
independent domains, static boundary adapters and activation/dependency rules.
This experiment shows why a correct extra cache is not automatically a useful
simplification. Keep the proof and tests, and audit repeated boundary rules before
introducing more mirrored state. The previous scoped I/O publication and
small-product guard experiments remain rejected as well.

The full hardware goal remains **21/30**, nine open. No hardware observation,
exclusive subsystem timing, real-time audio or default-engine gate closes.

## Frozen evidence and replay

[Evidence manifest](timer-deadline-budget-20261026/evidence.json) pins the candidate
C/WASM/build manifest, candidate and retained tests, full/targeted TAP outputs,
benchmark/control sources, all raw timings and restored source/artifact hashes.
Replay recalculates every ratio and schedule, checks every observation hash and
native ABI, and verifies the one changed build input.

```
node web-player/reports/timer-deadline-budget-20261026/replay.mjs
node web-player/reports/timer-deadline-budget-20261026/replay.mjs --check-current
node web-player/reports/timer-deadline-budget-20261026/replay.mjs --check-current --rebuild
node --test web-player/tests/device-timer-deadline-budget.test.mjs
```

The optional rebuild reconstructs pinned inputs in an ignored isolated folder,
requires byte equality with the archived candidate and reruns all 16 candidate
cases. It never installs the rejected candidate into production. `--check-current`
also requires the current production source/artifacts to match the recorded
restoration; omit it when inspecting this historical report after future changes.
