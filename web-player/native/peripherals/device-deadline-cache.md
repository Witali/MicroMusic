# Same-state device deadline cache

`device.c` now memoizes its absolute earliest hardware event. The original
scanner remains once as `next_event_scan()`. A separate valid bit permits caching
`UINT64_MAX` (no event). The entry is reusable only at the identical `board.base`
and without an intervening mutation. It is enabled by default and adds no public
configuration, instrumentation, imports or callbacks.

Every `elapse` and `service`, including zero-time calls, clears the entry before
doing work. Bus reads/writes, IRQ acknowledgment, control instructions, special
LPM, input insertion, reset acknowledgment and faults also clear it before
dispatch. Initialization clears the complete board. Reads are conservatively
treated as mutations because peripheral reads can advance state, expire windows
or lock ADC data. The complete dependency/transaction map is in
[the preceding design](device-deadline-cache-design.md).

The scanner may itself detect arithmetic failure; a faulted result is never
published. Public CPU-distance conversion and reset/hold/startup guards remain
outside the cache. The original event ordering, strict endpoint comparison and
zero-time servicing are unchanged. Pin history consumption and dirty-page
consumption may retain the entry because neither changes a scanner dependency.
There is no reuse across elapsed time and no analog same-time shortcut.

Code-placement checkpoint, 2026-10-25: the small lookup is now forced inline
while the full scanner stays separate. Cache state, invalidation and scanner
statements are unchanged. The final Clang/Binaryen image preserves this placement;
rhythmic measures 1.088x/1.086x on one host, with other gains unproven. All 1,704
regressions pass. See the [current audit](../deadline-dispatch-audit.md) and
[retained measurements](../../reports/deadline-dispatch-20261025.md).

The useful reuse is the endpoint scan immediately followed by the CPU bridge's
deadline publication, plus repeated same-state queries and the halted-wait loop's
initial scan. Each subsequent hardware service still performs a full scan.
Changes that introduce a scanner query inside a mutation transaction must clear
or suppress publication again before any later mutation in that transaction.

## Validation

`node --test web-player/tests/device-deadline-cache.test.mjs` includes the real
production `device.c` once in a focused C fixture and queries both the wrapper
and the single raw scanner on the same board. It primes before mutation and
checks invalidation, finite/infinite answers, zero-time service, clock phase,
NVM windows, sleep, asynchronous power reset and scan-time arithmetic faults.
There is no second scheduler or copied board-state oracle.

The same test builds the candidate to ignored `build/deadline-cache-test/runtime`
and loads the actual committed pre-cache WASM from Git, rather than constructing
a test-only uncached implementation. Baseline is
`f4aec2f:web-player/wasm/attiny13a.wasm`, 94,758 bytes, SHA-256
`2f44f950d742c66fbae466e1673da08a97ef893adcfc8ed404cc77ca2b726413`.
The comparison checks raw Float32 PCM bytes, complete CPU diagnostic state,
registers/I/O/SRAM, Flash, EEPROM, IRQ frames and remaining physical pin traces.
It covers `rhythmic`, `lumiere-stereo`, `hq4-chego-auto`, queued digital/analog
inputs, physical clock/OSCCAL/CLKPR and POR/BOD/reset abort/hold/release.

Before committing, the cache fixture plus `device-scheduler`, `device-clock`,
`device-osccal`, `device-bodcr`, `device-startup`, `device-power` and `nvm-voltage`
passed **82/82 tests**. The candidate build is 95,097 bytes (+339), import-free
with fixed two-page memory. The shipped WASM and its manifest are deliberately
unchanged in this focused source change. This establishes correctness evidence;
performance requires separate serial measurements of that actual baseline and
candidate.
