# Changed analog input propagation, 2026-10-23

The final runtime improves the external-clock kernel in every measured pair:
median paired speedup is1.300x at20MHz CLKPR/1 and1.447x atCLKPR/256. The
ordinary firmware results have substantial host variation; these measurements
do not establish a consistent firmware-wide speedup. Every retained comparison
matches the preceding runtime's PCM and architectural state exactly.

## Implementation

`pin_voltages` now injects only voltages different from the comparator's stored
PB0..PB5 inputs. This existing state also covers ADC-only pins, VCC-driven GPIO,
explicit analog overrides and reset, without a second cache. Changed inputs
keep their ascending pin order. If PB5 is unchanged, the final omitted input's
event-settling boundary is still serviced. ADC sampling therefore precedes an
equal-time voltage mutation, including a CLKI transition on PB3/ADC3.

Comparator/external trigger flags reach the ADC only when their levels change.
ADTS/ADATE register writes retain their own trigger detection. The generic
analog event scheduler still runs at repeated timestamps: a mutation can have
created zero-delay propagation. An experimental per-module equal-time guard
was removed after paired testing showed its branch cost could outweigh empty
advances on internal clocks. The retained optimization removes notifications
whose lack of change is already known by their caller.

The source edge queue, divider, CPU phases, pin ring, native audio collection,
IRQ ordering and official Microchip definitions are unchanged. No JavaScript
imports or per-edge callbacks were added.

## Reproducible evidence

Baseline: `a2bd135`,112340-byte WASM,
`ae66ad2e64f8e96af046cd02b04f49c82c371026b8686bd54647678c8a8efa97`.
Final implementation: `e32e518` following `66da952`,112522-byte WASM,
`ccbef473d1c5947c218215272b0a4312352a9e71c9ebc1851dec640c25f5f4f3`.
Both have103 exports, no imports and fixed two-page memory. The benchmark
verifies the original Git artifact and its source hashes, the current artifact
and source hashes, identical compiler/options/exports, and changes confined to
`peripherals/analog.c` and `peripherals/device.c`.

- [Paired raw timing, checkpoints and provenance](analog-propagation-20261023/benchmark.json).
- [Final native source-entry counts and chronological prefixes](analog-propagation-20261023/call-counts-and-prefix.json).
- [Baseline counts and original hotspot analysis](runtime-profile-20261023.md).

Host: Ryzen5 5600X, Windows10.0.26300 x64, Node22.22.3,
V8 12.4.254.21-node.56. Eight alternating baseline/candidate pairs per case,
176 timed runs after discarded warmups; fresh mutable state every time.
Construction, compilation, input submission, copying into retained PCM,
snapshots, assertions and hashing are outside timers. Only public capture or
run calls are timed. Full tests finished before timing; no other task test or
profiling run overlapped it. Host scheduling, GC, tiering and unrelated load
remain uncontrolled. Native diagnostic counts are separate from timing.

## Measured results

Firmware captures cover250ms at48kHz. Compatible uses the oscillator-half
contract; physical uses fixed ps and the resumable CPU. Direct kernels retire
one million instructions; clock kernels capture25ms at20MHz.

| Case | Baseline median ms | Final median ms | Median paired speedup | Paired min–max |
|---|---:|---:|---:|---:|
| rhythmic, compatible |434.49|405.09|1.032x|0.888–1.367x|
| rhythmic, physical |1118.92|1095.85|1.072x|0.969–1.231x|
| lumiere-stereo, compatible |397.03|392.03|1.043x|0.839–1.337x|
| lumiere-stereo, physical |612.72|674.86|1.063x|0.800–1.151x|
| hq4-chego-auto, compatible |410.13|401.11|0.997x|0.970–1.112x|
| hq4-chego-auto, physical |989.02|970.37|1.089x|0.955–1.433x|
| Kernel, compatible direct |224.43|233.14|1.030x|0.878–1.510x|
| Kernel, physical direct |447.22|386.87|1.137x|1.016–1.363x|
| Kernel, internal source /1 |194.20|174.80|1.097x|0.840–1.355x|
| Kernel, CLKI /1 |423.78|346.97|1.300x|1.199–1.573x|
| Kernel, CLKI /256 |306.59|209.93|1.447x|1.357–1.542x|

Paired speedup is the median of eight individual baseline/final ratios, **not**
the ratio of the two independent time medians. Both are retained in JSON.
Nonstationary host speed is visible: for stereo physical, the first three
pairs were about884–910ms versus790–822ms, whereas the last four were about
557–588ms versus530–559ms. A change between the middle pair's two runs reverses
the independent-median comparison. Firmware/direct-compatible gains are small
against this spread and should not be presented as established acceleration.
The CLKI paired ranges all exceed1. These are coupled CPU/peripheral/pin/audio
Node measurements, without DSP filtering; browser latency and exclusive
subsystem timings are not established.

## Work eliminated

These are C function entry counts, including entries later inlined by the
compiler, rather than WASM instruction counts or host calls. The diagnostic
build must match production PCM and full public/memory/IRQ state. No timing
from that instrumented build is used above.

| Scenario | Analog pin injections before → after | ADC advances before → after | ADC flag updates before → after |
|---|---:|---:|---:|
| rhythmic,250ms |112488 →18746|4506344 →2939289|1454563 →37494|
| lumiere-stereo,250ms |162198 →37494|4431250 →2843741|1419203 →37497|
| hq4-chego-auto,250ms |112494 →18747|6177657 →4061561|2003599 →37497|
| CLKI20MHz /1,25ms |6000000 →1000000|13902406 →5601604|1300802 →0|
| CLKI20MHz /256,25ms |6000000 →1000000|13005922 →5003948|1001974 →0|

Both CLKI cases still service all1000000 supplied transitions. The ADC receives
actual PB3 voltage changes even when ADC is disabled; no source edge or analog
phase was discarded to obtain this reduction.

## Accuracy and reproduction

The final full suite passed1139/1139 tests. Added regressions cover repeated-time
zero-delay propagation, reference/control/sleep changes, held trigger flags and
ADTS/ADATE writes, ADC sampling before equal-time voltage changes, GPIO/VCC/
override/reset propagation, and9600 private-state comparisons with the former
six-input path across three propagation delays and both initial comparator
outputs. Existing123-instruction, IRQ, PWM, reset, power and CLKI tests also pass.

All176 timed runs pass paired PCM-byte and full architectural comparisons at
640 endpoints, plus baseline determinism across trials. A separate untimed
2000-edge unequal CLKI waveform drives real PWM and free-running ADC3; all2001
pin events and five state checkpoints match the original runtime. Both PWM
outputs must go high and ADC3 must complete a conversion.

```powershell
node --test web-player/tests/*.test.mjs
node web-player/scripts/benchmark-analog-propagation.mjs --baseline-ref a2bd135 --trials 8 --out build/benchmarks/analog-propagation-final-20261023.json
node web-player/scripts/trace-device-calls.mjs --out-dir build/traces/analog-propagation-final
```

The broad performance/default-engine acceptance items remain open in
[the device plan](../native/ATTINY13A_PLAN.md). This optimization adds no external
programmer and makes no silicon timing claims.
