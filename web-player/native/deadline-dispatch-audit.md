# Deadline lookup and scan dispatch audit

Baseline: `cf9c91f6`, native SHA
`b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4`.
This extends the [same-state cache audit](peripherals/device-deadline-cache-design.md)
to the current CLKI and buffered-continuation paths. It does not authorize
reusing deadlines across elapsed time or changing the public I/O shadow contract.

## Existing reuse and mutation owners

The cache already avoids about two thirds of scanner entries. In the retained
[current-runtime trace](../reports/io-publication-scope-20261025/restored-trace.json),
250 ms of physical rhythmic performs 6,380,683 `next_event` entries versus
2,219,957 scans; HQ4 performs 6,670,132 versus 2,285,259. These are instrumented
source-entry counts, not exclusive times or optimized instruction counts.

Retain the cache key (`valid`, exact `base`) and scanner ordering unchanged.
Every elapse/service, including zero time, clears it before work. INIT, bus
READ/WRITE, IRQ acknowledgement, CONTROL/SLEEP/WDR/SPM, special LPM, queued
INPUT, RESET acknowledgement and FAULT retain their existing invalidation.
Reads can lock ADC results, expire control windows or advance peripherals.
Scan-time overflow must preserve its first fault and must never publish a cache.
CPU-distance conversion and reset/hold/startup/recovery guards stay outside it.

Current additions to the original audit:

| Path | Cache/observation constraint |
| --- | --- |
| CLKI source queue and periodic descriptor | Enqueue, horizon extension and descriptor submission invalidate INPUT. Refill can append a tail while querying the source; do not classify all getters as pure. Source-edge consumption runs through `advance_to` and the shared service invalidation. |
| CLKI CPU budget | `device_next_cpu_event` returns zero before querying the cache. No positive instruction span may extrapolate unknown future phases. Watchdog/NVM/power still use independent physical deadlines. |
| Buffered long internal spans | `advance_to_buffered_long` uses the same lookup at its loop head and endpoint. Pressure yields only after current-time events settle; preserve its original target/fault-accounting behavior. |
| Bounded resumable CPU | Keep strict budget/deadline comparisons, partial phases, pending IRQ and reset cancellation. Recomputing a CPU distance remains eager even if the absolute lookup hits. |
| Pin/audio/dirty-page consumers | Consuming history does not alter scanner dependencies. Queue pressure is a separate execution-yield condition and is never cached as a hardware event. |

## Selected experiment: code placement only

The exact optimized baseline merges the scanner into `next_event`: 3,351 bytes,
including a 16-byte native stack reservation before its cache-hit branch.
The wrapper has eight static call sites. Its cached answer is cheap, but still
enters that combined function. Changing cache lifetime would require additional
proof for all clock/domain/controller transitions; this experiment does not do it.

Add Clang `noinline` to the scanner declaration and `always_inline` to the small
wrapper declaration. Keep the scanner and wrapper statements byte-for-byte
unchanged. Do not combine this with publication suppression, module activity,
new device state, per-edge callbacks or a changed CPU ABI.

Exact rebuild/disassembly confirms the placement survives Binaryen O3: the old
wrapper body disappears; the scanner remains separately (3,258 bytes), with eight
conditional static call sites. Four callers grow; 198 other optimized bodies
are identical. Total WASM grows 671 bytes to 118,742. Exports/imports, fixed
memory/stack limits and generated CPU ABI remain unchanged. These observations
establish code placement, not speed or a working-memory saving.

The focused existing scheduler/deadline/buffer tests pass 34/34, all 15
production/candidate parity cases pass, and all 1,704 regression checks pass.
The placement tuning is retained at `741a1301`: rhythmic measures 1.088x/1.086x
in two intervals; other gains and small kernel losses remain inconclusive.
See [measurements, limits and replay](../reports/deadline-dispatch-20261025.md).
The ATtiny13A checklist remains 21/30; silicon and browser acceptance are separate.

Primary references: [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[pinned official device definitions](../vendor/microchip/ATtiny_DFP/3.4.278/README.md),
[Clang function attributes](https://clang.llvm.org/docs/AttributeReference.html#always-inline-force-inline)
and [WebAssembly binary control instructions](https://webassembly.github.io/spec/core/binary/instructions.html#control-instructions).
Compiler attributes guide optimization; the final WASM must be inspected rather
than assuming source-level inlining guarantees the result of later passes.
