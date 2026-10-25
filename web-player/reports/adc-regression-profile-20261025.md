# Matched sampling after the idle ADC change

The twelve profiles confirm that the compared kernel and HQ4 workloads match
the previous benchmark's CPU bytes, final state and PCM. They do **not** explain
the measured synthetic internal 20 MHz regression. The retained runtime remains
`b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4`;
no CPU/peripheral implementation or default engine changes in this checkpoint.
The full ATtiny13A plan remains 21/30, with nine items open.

## Comparable workloads and exact runtimes

The profiler previously used fastIdle=false for kernels and omitted the control
benchmark's queued input events. Its physical music setup also used a different
fuse/startup fixture and omitted the benchmark's NVM clock parameters. These are
valid separate workloads, but inappropriate for attributing the recorded loss.

`--benchmark-controls` selects the benchmark's fastIdle, fuse/NVM configuration
and timestamped input conventions. `--runtime-ref` loads a pinned native manifest,
WASM and all declared source inputs from Git into an isolated output directory.
The current checkout is not reset or rewritten. Every input hash and exact native
rebuild is verified before names are attached in a custom section. A full raw
diagnostic-state comparison is now included in the named/profiled oracle.

Two cases run against the pre-ADC native image `953024d5…` from `238aab2` and
the retained image `b6a67843…`: the physical internal 20 MHz /1 arithmetic kernel
renders 4,800 frames/100ms; HQ4 physical renders 48,000 frames/1s, both at 48 kHz.
Each case/version has three sequential profiles at a requested 1 ms interval.
Construction, lowering, warmup, comparison, hashing and serialization are outside
sampling. The host is Windows/Ryzen 5 5600X with Node 22.22.3 and the pinned
Clang 24/Binaryen 133 SDK. Host load/tiering/frequency remain uncontrolled.

All twelve named/profiled runs match their own uninstrumented references on PCM,
complete public/diagnostic state, data/Flash/EEPROM and IRQ frames. Both native
versions also match each other and the retained longer benchmark on generated
CPU hash, final public state and PCM. This is model equivalence, not silicon
calibration or an independent capture of every physical pin edge.

## Observations and limits

There are 13,723 samples with the public capturePhysical ancestor: 841/680 for
the old/new kernel and 6,837/5,365 for old/new HQ4. Percentages below pool the
three runs per case/version. Inclusive percentages overlap and cannot be added.
Source ownership identifies surviving optimized bodies, not pure subsystem cost.

| Surviving body | Kernel old/new self | HQ4 old/new self |
| --- | ---: | ---: |
| next_event | 11.18% / 8.53% | 12.46% / 12.51% |
| ratio | 4.40% / 4.12% | 5.68% / 6.04% |
| duration | 4.04% / 4.85% | 5.21% / 6.45% |
| service_clocks | 7.49% / 3.82% | 4.12% / 3.24% |
| mirror | 4.64% / 3.53% | 3.72% / 3.15% |
| analog_advance | 3.21% / 3.82% | 3.50% / 3.54% |
| analog_adc_advance | 1.07% / no observed leaf | 1.30% / 0.04% |

The analog aggregator's inclusive share is 5.35%→5.74% for the kernel and
6.32%→4.92% for HQ4. The kernel has only 841/680 work samples and large run/gap
variation. Its apparent percentage changes do not isolate a 6% cost increase.
Unchanged bodies also change sample shares; percentages are not exclusive times.
Absence of a sampled leaf is not proof of zero calls. Profiled wall times are
not balanced speed measurements. The prior uninstrumented 0.942x kernel result
therefore stays an unresolved performance limitation.

Raw verification exposed an output-identity issue in the pooling tool: it grouped
by frame key correctly but omitted that key from output rows. Same-named frames
with different URLs consequently became ambiguous to downstream verifiers.
The output now retains the key. Pooling values and native leaf findings do not
change; both analysis modes (with and without separate counter traces) are
checked. The comparative analyses use no unrelated counter trace.

## Publication audit

Disassembly of the exact retained mirror body contains one 32-bit pointer load
and 31 byte stores. The compiler already caches the data pointer, so a proposed
local pointer substitution would add no demonstrated opportunity and is not
implemented. Addresses in the retained register inventory come from the generated
official Microchip map; native BSS addresses are not AVR register addresses.

Sixteen published bytes change through software/bus/reset actions rather than
ordinary counting. However, three new tests show that public clock service
restores these controller-owned I/O bytes even after direct mutation of the
exported data view. Compatible/internal physical clock and bounded CLKI all
pass, source time actually advances, and CPU-owned r17 remains unchanged.
The focused result is 3/3; no new complete 1696-test run is claimed.

Simply omitting those stores would change observable behavior. The next candidate
is an explicitly owned execution scope that retains existing publication at
public/partial/fault/reset boundaries and full publication at configuration
mutations. It needs dedicated admission tests, including zero-work calls, before
any stores are skipped. [The detailed ownership audit](../native/io-publication-audit.md)
records writers, cross-register effects and observation constraints. This is a
concrete next implementation contract, not an implemented optimization.

## Retained evidence and replay

[Evidence](adc-regression-profile-20261025/) includes four source summaries,
both pooled analyses, both named CPU modules, native name maps, the exact mirror
WAT/source and official-address inventory, tool/test snapshots and the 3-test TAP.
All twelve raw profiles are retained losslessly as gzip, with compressed and
original hashes in raw-manifest.json. Summary paths retain their original ignored
output locations; the manifest maps them to the compressed copies. The verifier
recomputes every native frame's self/inclusive counts from the raw profiles,
reconstructs named native hashes from pinned Git binaries/name maps, and checks
benchmark equivalence and publication evidence.

Profiler/control support is `3b10842f`; output frame keys are fixed at `8a99fac9`.
Publication tests are `ac738d45`. Native remains the earlier `14da787` build.

```sh
node web-player/reports/adc-regression-profile-20261025/verify-evidence.mjs
node web-player/scripts/profile-device.mjs --kernel --clock physical --frequency 20000000 --divisor 1 --frames 4800 --repeats 3 --benchmark-controls --runtime-ref 238aab2 --out-dir build/profiles/replay-old-kernel
node web-player/scripts/profile-device.mjs --kernel --clock physical --frequency 20000000 --divisor 1 --frames 4800 --repeats 3 --benchmark-controls --out-dir build/profiles/replay-kernel
node web-player/scripts/profile-device.mjs --firmware hq4-chego-auto --clock physical --frames 48000 --repeats 3 --benchmark-controls --runtime-ref 238aab2 --out-dir build/profiles/replay-old-hq4
node web-player/scripts/profile-device.mjs --firmware hq4-chego-auto --clock physical --frames 48000 --repeats 3 --benchmark-controls --out-dir build/profiles/replay-hq4
node web-player/scripts/analyze-device-profiles.mjs --input build/profiles/replay-kernel --input build/profiles/replay-hq4 --without-calls --out-dir build/profiles/replay-analysis
node --test web-player/tests/device-io-publication.test.mjs
```

Use the recorded tool/native revisions for historical replay. No browser audio
underrun gate is run and no real-time profile is newly supported. Official register
basis: [ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and [pinned DFP 3.4.278 definitions](../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
The host publication policy is an emulator contract, not a silicon timing claim.
