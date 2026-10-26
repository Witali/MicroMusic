# Watchdog-period reduction: rejected

Exact period-based watchdog conversion passes all1681 tests and the expanded
15-case parity matrix, but the four measured medians are0.997x/0.993x/0.976x/
0.961x. No speed gain is established. Production C/WASM are restored to
`77c354b`, retaining the earlier physical ps→ns improvement. Four new clock
regressions and two active-watchdog ISR benchmark cases remain.

## Candidate and correctness

For fixed base frequency B and watchdog rate R, when R divides B exactly, the
original numerator remainder is a multiple of R. Cache P=B/R and store phase
in base-time units. Split delta into quotient/tail before adding the old phase;
carry once when tail>=P. A delta<P guard avoids division for short spans.
P<=1e12, so the two tails fit uint64. Other rates keep the original general
rational algorithm, including its overflow checks. The oscillator coordinate
continues advancing while the watchdog counter is disabled.

Every inverse consumer must convert phase back to numerator units: the watchdog
timeout scanner, internal reset/startup pulse calculation and external CLKI
startup. The last consumer resides in the device-specific include, rather than
device.c. A private uint64 period field adds8 bytes of state; no working-memory
saving is claimed. No AVR instruction emission, original cycles or source-edge
processing changes, and no handwritten assembly is introduced.

The four tests compile actual device.c and its peripheral modules to WASM.
They cover nine physical/legacy frequency configurations, divisible/arbitrary
rates, uint64 boundaries and diagnostic ordering,4500 cumulative disabled-clock
intervals, timeout endpoints, internal pulse offsets and external CLKI SUT
delays with fractional phases. The arithmetic fixture isolates clock conversion;
it does not replace the full device/source-phase tests. Candidate full suite:
1681/1681, zero skips,89.20s. After restoring production, all four new tests
pass again; the baseline's1677-test full run is recorded in the preceding
[retained ps→ns report](physical-ns-remainder-20261025.md).

The expanded untimed matrix covers15 workloads,30 runs and176 snapshots
(88 reference comparisons), with exact PCM, architectural/diagnostic state,
SRAM/Flash/EEPROM, IRQ frames and pin history. Existing internal/CLKI/divisor
and enabled-ADC cases remain. Both new20MHz /1 watchdog cases execute their
real ISR with global interrupts enabled. The fixture uses generated Microchip
MASK/VECTOR values: ATtiny13A's WDT index8 is already a word PC, byte offset16.

## Exact binary and timing evidence

Baseline native SHA-256:
`953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0`.
Rejected candidate:
`bb2885077843d09ca030579cefa6e503055b1092eb862f24b4f584f7a4d45565`.
Size117975→118183 bytes (+208). Compiler/options, official DFP3.4.278 inputs,
109 function exports, fixed two-page memory,8192-byte stack and no host imports
are unchanged. Only device.c and attiny13a/clki_board.inc change among inputs.
An isolated pinned-SDK rebuild reproduces the candidate byte-for-byte.

Exact optimized function comparison finds195 identical and eight changed bodies.
Elapse grows489→575 bytes, next_event3351→3367, reset_startup778→808 and
avr_reset4525→4601. Other changes include relocated configuration data addresses
after the private struct grows; eight changed bodies does not mean eight new
arithmetic implementations. Node's recorded V8 options disable experimental
WASM inlining by default. Crossing its advertised500-byte inlining limit alone
therefore does not explain these measurements; no compiler-cause claim follows.

Windows/Ryzen5 5600X, Node22.22.3, Clang24/Binaryen133 from Emscripten6.0.12.
Direct-emitter CPU bytes are identical across native versions; optional bounded
regions and phase-local liveness stay off. Each row has eight balanced trials
and four warmups per oldA/oldB/newA/newB label, with shared native Modules inside
identity pairs and fresh CPU Modules/instances. Construction, checksums and
snapshots are outside timers. Tests/builds/profiling are separate. Host load,
affinity, frequency and GC are uncontrolled. Real firmware renders12000 frames
at48kHz with IRQs active; the CLKI watchdog kernel renders1200 frames.

| Workload | Old/new median | Paired range | Old identity | New identity |
| --- | ---: | ---: | ---: | ---: |
| rhythmic compatible | 0.997x | 0.976–1.080 | 1.042x | 0.989x |
| rhythmic physical | 0.993x | 0.769–1.145 | 1.063x | 1.033x |
| HQ4 physical | 0.976x | 0.911–1.050 | 1.022x | 0.962x |
| CLKI20MHz /1, watchdog ISR | 0.961x | 0.893–1.042 | 1.009x | 0.985x |

All128 timed runs and64 warmups retain1824 snapshots/1786 comparisons.
These noisy negative screens justify rejecting an unproven optimization, rather
than claiming a stable slowdown or completing the15-case timing matrix. No
browser audio/underrun gate is rerun, no real-time support is claimed, and the
default engine stays `wasm`. Hardware/model completeness remains21/30.

## Reproduce and continue

[Archived inputs/results](watchdog-period-20261025/) retain the rejected source,
binary/manifest, exact rebuild helper, test/full TAP, restored focused TAP,
harness, raw validation/timings, optimized-function comparison and V8 options.
Tests are committed at `41c9936`; the harness/unit note at `e371c5d`.

```sh
node web-player/reports/watchdog-period-20261025/verify-evidence.mjs
node web-player/reports/watchdog-period-20261025/rebuild-candidate.mjs
```

The benchmark's `--baseline-ref 77c354b --change-set watchdog-period` selector
requires the archived candidate's two changed inputs and matching manifest/
binary, so it intentionally rejects the restored production checkout. Use an
isolated reproduction checkout for timing; do not mix candidate sources with
the production manifest. `validation.json` and `screen.json` retain all workload
parameters and source hashes; the screen selects the four rows above.

Next audit lazy synchronization of the free-running watchdog coordinate while
its counter is disabled. Preserve fractional phase, inactive-history discard
before enabling, WDR/MCUSR/WDTCR effects, reset/startup and fault timing. Keep
the original arithmetic eagerly when a deferral could hide an overflow fault.
This next implementation is untested; an audit is required first.

Primary references: [Microchip ATtiny13A DS40002307A, sections6.2,8.4–8.5,9.1](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
documents watchdog-based startup, counter modes and word-addressed vectors;
[WASM integer semantics](https://webassembly.github.io/spec/core/exec/numerics.html)
defines native-width operations. The continuously advancing off-state oscillator
coordinate is the existing model contract, not a newly measured silicon phase.
