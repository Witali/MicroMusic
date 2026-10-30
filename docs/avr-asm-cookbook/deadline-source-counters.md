# Count deadline queries and invalidation causes

Target: the full ATtiny13A native WASM model, internal and external clocks,
using the pinned device build manifest and prepared SDK. This is untimed
diagnostic tooling. It changes no production source, ABI, compiler identity,
device behavior or site configuration and adds no per-event JavaScript call.

Run `trace-device-calls.mjs --deadline-counters` to instrument ignored copies
of native C. Besides source-level function entries, record:

- Cache queries split into actual hits and misses; every miss must enter and
  exit the original scanner once.
- Invalidation attempts by the original `deadline_reason` enum, plus attempts
  that actually clear a valid cache. Enum order is read from the original C.
- Reasons accumulated since the preceding miss. These overlap: ELAPSE and
  SERVICE can both describe one miss. Do not sum them as disjoint causes.
- Half-deadline conversion outcomes: infinity, already due, unknown future CLKI
  edge or internal-clock conversion. CLKI must not extrapolate edges from Hz.
- `duration` entries inside versus outside the scanner, with balanced diagnostic
  scope tracking around its checked single return.
- Zero/positive/backwards elapsed spans and the subset of zero spans whose
  same-base valid cache already proves the next event lies in the future.

Counters reset after construction and input submission; pending-reason state
also resets. A first miss without a recorded reason can therefore be legitimate.
The first 256 chronological entries are a bounded prefix, not the whole trace.
Counts include C entries inlined by O3; they are neither WASM call counts nor
exclusive costs. Instrumentation changes layout/performance, so do not time it
as a replacement for uninstrumented balanced controls.

The [current evidence](../../web-player/reports/deadline-counters-20261030.md)
contains nine instrumented workloads and seven default-counter controls.
Full recorded state, memory, PCM and retained tail-pin data match production.
All 490 shared source-entry counts also match between control modes.
This does not replace full waveform acquisition or silicon measurements.

The data identifies zero-duration arithmetic as a bounded candidate. A future
experiment can test an early return from the arithmetic in `elapse` when
`delta == 0`, while retaining invalidation and subsequent event servicing.
Prove fraction/overflow/fault behavior before keeping it. A future-deadline
certificate alone is not permission to skip `service`: wake checks, publication
and shared public state still need their original contract. No such optimization
is enabled by this counter work, and no execution-speed gain is inferred.

Reproduce in separate fresh ignored directories:

```text
node web-player/scripts/trace-device-calls.mjs --physical-firmware --deadline-counters --out-dir build/traces/deadline-replay
node web-player/scripts/trace-device-calls.mjs --physical-firmware --out-dir build/traces/deadline-control-replay
node web-player/scripts/verify-deadline-counters.mjs --input build/traces/deadline-replay/summary.json --control build/traces/deadline-control-replay/summary.json
```

The auditor verifies current production/native/source hashes, complete typed
counter tables, query/scan/exit and conversion partitions, reason summaries and
common source counts/output hashes. Retained reports require their recorded
source revision when replayed after a later implementation change.
