# Lazy watchdog clock: rejected after activation tracing

The prototype preserves the tested model but does not establish a speed gain.
Production returns to `2c52cc1`'s native sources/binary, retaining physical ps→ns
reduction. Six additional watchdog regressions, the historical benchmark selector
and improved source-entry tracing remain. This is an execution experiment;
hardware/model completeness stays 21/30, with nine items open.

## Algorithm and verification

While WDE/WDTIE are clear and rate R<=fixed base frequency B, skip oscillator
conversion in `elapse`. Retain the existing numerator remainder, plus a private
last-synchronized timestamp and eligibility byte. Catch up using elapsed delta
before WDTCR/MCUSR observations/mutations, WDR, reset/hold and both internal/CLKI
startup calculations. Discard the disabled interval from the module's counter
before a write enables it. Preserve the independent free-running phase.

For valid zero-epoch state, floor(base*R/B) fits uint64 when R<=B; rates above B
remain eager so overflow faults keep their original timestamp. Post-fault clock
continuation also remains eager in the original source→ns→watchdog order.
Ordinary watchdog service still updates CPU write-window expiry, including the
second same-time CLKI service after a delivered CPU phase. No physical source
transition, original AVR cycle, IRQ/reset boundary or output consumer is removed.
The off-state phase is the existing digital model policy, not measured silicon.

All **1,687 tests pass**, zero skips, 136.99s. Ten focused clock tests include
the prior BigInt/uint64/fraction/startup oracles plus 500-interval bursts,
off→on→off→on timeout endpoints, WDR, WDCE expiry with a disabled counter,
EXTRF/WDRF/WDTON and eager high-rate overflow. The candidate fixture explicitly
observes/rebases its private cache when testing independent uint64 intervals.
Candidate-only lag assertions prove deferral activates. Retained tests keep the
architectural oracles without depending on the rejected cache; all ten pass
again on restored production. No new full-suite baseline run is claimed.

The complete untimed 15-case matrix passes 30 runs/176 snapshots (88 comparisons):
PCM, full architectural/diagnostic state, memory, IRQ frames and pin history
match. It includes internal/CLKI/divisor, enabled ADC and both actual watchdog
ISR controls. Generated CPU bytes and ABI match across the native versions.

Baseline SHA-256:
`953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0`.
Rejected candidate:
`c3995caa57e94c5618153dd906bf5b4366870a26f93caf517c84e80dc44a62e0`.
Size 117,975→119,377 bytes (+1,402). Clang24/Binaryen133, pinned Emscripten6.0.12
options, official DFP3.4.278, 109 function exports, no host imports, fixed two-page
memory and 8,192-byte stack remain unchanged. The private state grows; no memory
saving is claimed. Only device.c and the ATtiny13A clki_board.inc change among
native inputs. An isolated rebuild reproduces the candidate byte-for-byte.

Static comparison finds 168 identical bodies, six normalized relocations and
29 changed bodies, with no additions/removals. Helpers inline into consumers:
elapse 489→553 bytes, device_read 1451→1675, full_write_io 5131→5375,
reset_startup 778→1104. Many other changes are state/configuration address
operands after struct growth. This is not proof of the measured runtime cost.

## Controlled timing

Windows/Ryzen5 5600X, Node22.22.3. Eight balanced trials and four warmups for
each oldA/oldB/newA/newB label; native Modules are shared inside identity pairs,
CPU Modules/instances are fresh. Optional bounded regions and phase-local
liveness stay off. Construction, snapshots and hashes are outside timers.
Tests/builds/profiling run separately. Host load, affinity, frequency and GC
are uncontrolled. Real firmware renders 12,000 frames at 48kHz with IRQs active;
direct kernels retire 1M instructions, framed kernels render 1,200 frames.

| Workload | Old/new median | Paired range | Old identity | New identity |
| --- | ---: | ---: | ---: | ---: |
| rhythmic compatible | 0.988x | 0.948–1.019 | 1.006x | 0.992x |
| rhythmic physical | 1.005x | 0.864–1.072 | 0.981x | 1.010x |
| HQ4 physical | 1.020x | 0.924–1.487 | 1.034x | 0.983x |
| CLKI20MHz /1, watchdog ISR | 0.968x | 0.838–1.026 | 0.998x | 0.960x |
| direct compatible | 1.016x | 0.944–1.039 | 1.014x | 1.016x |
| direct physical | 1.025x | 0.957–1.109 | 1.005x | 1.001x |
| CLKI20MHz /1 | 0.973x | 0.808–1.045 | 1.015x | 0.995x |
| internal20MHz /1 | 1.081x | 0.814–1.249 | 0.990x | 0.982x |

The two disjoint screens retain **256 measured runs, 128 warmups, 2,112 exact
snapshots and 2,068 reference comparisons**. Apparent positive medians overlap
substantial variation; internal-kernel identity ranges reach 0.771–1.285 and
0.737–1.214. HQ4 has an old identity outlier of 1.949. No repeatable real-firmware
gain is established, so further timing/default activation is unwarranted. A
stable slowdown is not established either. No browser audio/underrun gate is
rerun or real-time support claimed; default engine remains `wasm`.

## Activation and next target

Separate source-entry instrumentation compares each counted runtime against
its uninstrumented native version in five physical cases. Both sides pass PCM,
full public/diagnostic state, data/Flash/EEPROM, IRQ and pin-history checks.
Across versions, PCM/pin hashes, elapsed source-entry counts and CPU cycles
also match. Counters include entries later inlined by O3; they are not WASM
call counts, exclusive timings or benchmark results.

| Physical workload | Old watchdog `rational` entries | Candidate | ADC advance entries, unchanged |
| --- | ---: | ---: | ---: |
| rhythmic | 2,135,496 | 0 | 4,408,529 |
| lumiere-stereo | 2,142,132 | 0 | 4,500,492 |
| HQ4 / actual hq4-chego-tiny | 2,248,976 | 0 | 4,596,267 |
| CLKI20MHz /1 | 1,300,802 | 0 | 5,601,604 |
| CLKI20MHz /256 | 1,001,974 | 0 | 5,003,948 |

In physical mode nanosecond conversion has no `rational` call, so these removed
entries are watchdog conversions. Candidate `watchdog_sync` entries are also
zero during capture: no phase consumer forces catch-up in these images/spans.
Thus inactivity admission works; these counts do not explain why timing fails
to improve. Recurring watchdog-module, ADC, scanner and publication work remains.

The tracer now resolves catalog aliases, pins requested/actual firmware IDs and
Flash hashes, records catalog/host sources, checks full diagnostics/pins and
correctly labels internal physical timestamps as picoseconds. Fixes are at
`cccf9c3`; retained tests/historical benchmark selector at `1c3910e`.

Next audit the inactive ADC path and its aggregator dependencies before another
clock-arithmetic experiment. The counts identify frequent work, not its exclusive
cost or how much can safely disappear. See [ADC activity audit](../native/adc-activity-audit.md).

## Reproduction

[Archived inputs/results](watchdog-lazy-20261025/) retain both source versions of
the tests, candidate C/WASM/manifest, full and restored focused TAP, harness,
timings, both trace summaries, exact rebuild helper and optimized-function diffs.

```sh
node web-player/reports/watchdog-lazy-20261025/verify-evidence.mjs
node web-player/reports/watchdog-lazy-20261025/rebuild-candidate.mjs
node web-player/scripts/trace-device-calls.mjs --physical-firmware --out-dir build/traces/current
```

The benchmark selector `--baseline-ref 2c52cc1 --change-set watchdog-lazy`
requires the candidate's two changed inputs and matching native manifest/binary;
it intentionally rejects restored production. Recreate those inputs in an
isolated checkout to repeat timing. Both timing JSON files retain all parameters
and exact case selections. Trace summaries retain the instrumented image hashes;
raw counted binaries/prefix build files stay under ignored build/traces/.

References: [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections6.2 and8.4–8.5 for watchdog startup/control;
[WASM integer semantics](https://webassembly.github.io/spec/core/exec/numerics.html).
