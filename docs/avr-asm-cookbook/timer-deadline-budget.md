# Timer deadline round trip: exact arithmetic, rejected cache

Applicable to the ATtiny13A native board's internal clock profiles. Microchip
DS40002307A sections 6 and 11 describe the clock/prescaler and Timer0 domains.
This technique concerns the emulator's integer deadline conversions, not a new
assumption about undocumented silicon phases.

Let `D` be base-frequency units times CLKPR divisor, `r` the oscillator half-edge
rate, `p` the retained phase (`0 <= p < D`) and `n > 0` the number of virtual
half edges until a synchronous Timer0 deadline. The scheduler converts to a
base-time distance:

```
t = ceil((n*D - p) / r)
```

If `0 < r <= D`, then

```
n*D <= t*r + p < n*D + r <= (n+1)*D
floor((t*r+p)/(2*D)) = floor(n/2)
```

Thus, when Timer0's converted timestamp equals the earliest board event, its
whole-CPU-cycle distance can be obtained without the inverse ratio. An
asynchronous event at the same timestamp gives the same budget. An earlier
asynchronous event must use its original conversion. Already-due events have
zero distance. CLKI, overspeed synthetic clocks, invalid/overflowing timestamps
and out-of-range cached distances retain their original paths.

An experimental cache stored a flag and uint32 cycle distance in existing
padding of the 24-byte same-state deadline record. It was valid only at the same
base timestamp and under all existing invalidation rules; no reuse across elapsed
time was attempted. CPU/native ABI, two-page linear memory and strict event-end
guards stayed unchanged. The WASM image grew by 189 bytes.

**Rejected after measurement.** All 1888 candidate regressions passed. The
six-workload screen used Clang 24 / Binaryen 133, Node 22.22.3 / V8 12.4 on a
Windows Ryzen 5600X, 192 timings and 96 warmups with four-label Williams order.
Real-firmware median ratios were 1.010x, 1.007x and 0.991x, without convincing
gains over identity variation. CLKI measured 0.965x (all eight pairs slower),
while the internal kernels showed higher ratios with substantial identity
variation. The experiment did not pass the real-workload/control gate.

Production Git inputs were restored, with exact WASM bytes and LF-normalized
source/manifest identities. Retained tests
exercise the actual production board against the pinned previous conversion and
an independent BigInt formula across frequencies, CLKPR values, fractional phases,
adjacent 1-ps event ties, asynchronous controllers, CLKI and overflow. Synthetic
overspeed/wide-distance cases verify arithmetic fallback rather than hardware
support. The source-only arithmetic proof is reusable; the rejected cache must
not be treated as an accepted optimization.

[Full report, frozen candidate and replay](../../web-player/reports/timer-deadline-budget-20261026.md).
No new assembly is introduced; the selectable C/WASM and JS paths remain.
These Node measurements do not establish browser audio support or underrun
behavior. References: [Microchip datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and [WASM integer numerics](https://webassembly.github.io/spec/core/exec/numerics.html).
