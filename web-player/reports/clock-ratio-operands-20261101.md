# Actual clock-ratio paths and operands, 2026-11-01

Nine current-runtime workloads execute **30754561** clock-ratio source entries:
30606126 use the original native-width path and 148435 use wide decomposition.
**None executes the long-division loop.** Music prefixes use only the short
path. Further wide-loop optimization cannot benefit those observed music calls;
inspect repeated short conversions and their callers before another candidate.
These are branch counts, not exclusive times or a measured speedup.

Production C, native artifacts, compiler/cache identity and defaults remain
unchanged from `15ebdf40`. This advances the diagnostic part of stage 5 without
closing it; the full-device plan stays **24/31 complete, seven open**.

## Workloads and results

Both control and operand builds use the current registered manifest/toolchain,
physical/resumable clocks, bounded regions, phase-local optimization and the
existing deadline counters. Music runs are 12000 frames at 48 kHz, with nominal
catalog clocks and fast idle. CLKI kernels run 1200 frames, periodic 20 MHz
source edges at /1 or /256; /1 also covers enabled-idle and converting ADC.
Internal 20 MHz kernels run one million instructions with ADC off/converting.
These are explicit diagnostic policies, not the conservative verification preset.
They are shorter prefixes than the earlier 100M/262144-frame sampled workloads.

| Workload | Ratio entries | Short path | Wide decomposition | Long division |
| --- | ---: | ---: | ---: | ---: |
| Rhythmic physical | 10003134 | 10003134 | 0 | 0 |
| Lumière stereo physical | 10425240 | 10425240 | 0 | 0 |
| HQ4 physical | 4488555 | 4488555 | 0 | 0 |
| CLKI /1 | 1305604 | 1305604 | 0 | 0 |
| CLKI /256 | 1006776 | 1006776 | 0 | 0 |
| CLKI /1, ADC enabled-idle | 1305604 | 1305604 | 0 | 0 |
| CLKI /1, ADC converting | 1305604 | 1305604 | 0 | 0 |
| Internal direct | 125004 | 93753 | 31251 | 0 |
| Internal direct, ADC converting | 789040 | 671856 | 117184 | 0 |

All observed wide decompositions succeed; no zero-divisor or quotient-overflow
branch executes in these workloads. The standalone tests exercise every path,
including failure and long-division paths, separately.

The complete operand groups are retained in the
[operand capture](clock-ratio-operands-20261101.json). For each original `(b,d)`
in `(a*b+carry)/d`, they retain calls, min/max `a` and carry, zero `a`, zero carry,
`a <= UINT32_MAX` and `carry < d` counts. These classes overlap; group statistics
are not joined to individual branch paths. All nine workloads fit the 32-group
capacity with zero untracked calls.

Music has five groups: sample frames to ps, CPU halves to ps, source phase at
denominator 1e12/2e12 and watchdog phase. For example, Rhythmic's
`(b=1e12,d=19200000)` group has 3611042 calls with `a=1..382`, all carry zero.
Its source-phase `(19200000,1e12)` group has 2256951 calls, including 574252
zero-`a` entries and carries up to 999993600000. Neither observation justifies
skipping service or reinstating the rejected zero-product guard.

The internal direct group `(40000000,1e12)` observes `a` as large as
`UINT64_MAX-1`, consistent with the finite unbounded-CPU-deadline calculation in
`avr_device_cpu_deadline`/`device_cpu_halves_until_ps`. This is not a huge elapsed
simulation step. Preserve that finite-timeline admission and all overflow/fault
behavior when considering a different conversion path. The grouped data does
not by itself attribute each call to a caller.

## Correctness and retained identities

Nine operand runs and nine counter controls each match their own uninstrumented
production reference: **18 parity pairs / 36 core executions**. Checks cover
PCM, full recorded public/diagnostic state, SRAM/GPR/Flash/EEPROM, IRQ frames
and retained tail pins. All **1107 common source-entry counts** and output hashes
also match between operand and control modes. The first-256 diagnostic entry
prefix changes when extra entries are added; it is not an equality target.
This does not establish complete pin-waveform, audio-underrun or silicon fidelity.

All **35 focused checks** pass: eight new counter tests plus the existing clock,
deadline-cache and ns-clock checks. The instrumented arithmetic passes **6029**
independent BigInt comparisons and **72** delay/phase/rounding cases. Tests
exercise every actual ratio path, preservation of failed-call outputs, extrema,
overlapping classes, table overflow/reset and invalid source/data rejection.
Four real CLI corruption controls reject broken path budgets, group budgets,
different execution policy and another native hash.

The [evidence](clock-ratio-evidence-20261101.json) binds tests, producer/auditor,
native inputs, compiler graph, raw captures and counted binaries. The
[control capture](clock-ratio-control-20261101.json) and operand capture are exact
completed producer summaries, with LF checkout attributes for stable byte hashes.
Raw C copies, binaries and logs remain ignored. No new dependency was downloaded.

Production native remains 124590 bytes, SHA-256
`244b3d3da85ff6cd065e6b105b18d26d8ae07e6615802d77f23a123338209c98`;
compiler/cache identity remains
`6dff8aef30a8847d4abb3dad56d0d12d52889ac034c9cab42c13611121545a5d`.
Both counted modules have zero host imports, retain original exports and fixed
two-page memory. Their extra diagnostic exports are not a production ABI change.
The prior 2862/2862 runtime checkpoint belongs to unchanged production; the full
suite was not rerun for this offline change. No official simulator session ran.
The 10 ns contract concerns virtual verification events, not these counters.

## Reproduction

Use the already registered Emscripten 6.0.12 SDK. Commands preserve production
files and compile only ignored copies:

```text
node web-player/scripts/trace-device-calls.mjs --physical-firmware --bounded-regions --phase-locals --deadline-counters --out-dir build/traces/ratio-control-replay
node web-player/scripts/trace-device-calls.mjs --physical-firmware --bounded-regions --phase-locals --deadline-counters --ratio-counters --out-dir build/traces/ratio-operands-replay
node web-player/scripts/verify-deadline-counters.mjs --ratio-counters --input build/traces/ratio-operands-replay/summary.json --control build/traces/ratio-control-replay/summary.json
```

The retained captures can be audited directly with the last command's input paths
replaced by their report paths, using their recorded source revision. Focused
checks run with `node --test` on `clock-ratio-counters.test.mjs`,
`device-clock.test.mjs`, `device-deadline-cache.test.mjs` and
`device-ns-clock.test.mjs` under `web-player/tests/`.

Instrumentation changes code layout and execution cost. Do not time these
builds as production or convert counts into elapsed-time percentages. A future
runtime change still needs exact event/output parity and balanced uninstrumented
controls; the previously rejected multiply, zero and checked-overflow candidates
remain rejected.
