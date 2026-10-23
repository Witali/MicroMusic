# Deadline cache: serial baseline/candidate measurement

The same-state cache from `55f45c3` improved the measured coupled device capture
on three firmware excerpts, with byte-identical results. These are Node results
on one host, with substantial host variance, rather than browser performance or
exclusive CPU/peripheral timings.

## Runtime and method

Measured on 2026-10-23 with Node **22.22.3**, V8 **12.4.254.21-node.56**, Windows
10.0.26300 x64, **AMD Ryzen 5 5600X**, 12 logical CPUs, reported 3693 MHz.

| Artifact | Baseline | Candidate |
| --- | --- | --- |
| Source commit | `f4aec2f5effd33fc4dfd926d2c33649d945a1490` | `55f45c35b4f37fc8b49ee965d096da29e923be3d` |
| WASM bytes | 94,758 | 95,097 (+339) |
| WASM SHA-256 | `2f44f950d742c66fbae466e1673da08a97ef893adcfc8ed404cc77ca2b726413` | `f7fe722207d066c7fdf980b7d38bb8506256a696a4fd21c59fee235a6e3e9ddd` |
| Source-input map SHA-256 | `46b65a5da79b6bdea1651bc8409392d8cf3e8d9781d8df53d07065ef90bbd4bf` | `eaa73c7d70b4d4376a5bab4f9d20b7df77ba21bd1c23d657773cfbe8d12ca205` |
| Normalized `device.c` SHA-256 | `5b0a3fb99380bbef314fd06ed2cca2e8e3cb9058e163e56a0c364cef673ddf5c` | `4e1032e22b7df6c7ca9c6f2dc62db389d927ea051868da40edd9ee8f1d35c92d` |

Both builds use the same compiler, `-O3` flags, native source list and export
surface. The only changed compiled input is `device.c`. The benchmark reads the
actual baseline WASM and manifest from Git, verifies each historical source blob
against that manifest, and verifies every current candidate input against its
separate build manifest. Both runtimes have no host imports and fixed two-page
memory. JS uses root's profile separation at `822d923`; its hashes, firmware
hashes, complete native manifests and Node versions are in the raw reports.

Each run starts from a fresh device and captures **48,000 frames at 48 kHz** in
1024-frame blocks, with `fastIdle:true` and `optimizeFlags:true`. After one
discarded 4096-frame warmup per runtime/firmware, six trials alternate baseline
then candidate and candidate then baseline. Construction must hit the production
translation cache into fresh memory. Runtime/CPU module compilation, construction,
retained PCM copying, snapshots, hashing and checks are outside capture timers.
Generated CPU WASM bytes were identical between baseline/candidate per firmware.

Only production `capturePhysical` calls are timed. They couple translated CPU,
native clock/scheduler/peripherals, physical pin integration, audio collection,
and JS entry/output copy. There is no per-instruction JS callback or profiling
instrumentation. DSP filtering is not measured. Runs receive matching queued
digital and analog inputs.

Two serial passes use (1) the physical fixed-picosecond contract with an explicit
nominal CAL0 frequency of 9.6 MHz, all other CAL values unspecified and the
fixed-ns NVM profile, and (2) the compatible fixed oscillator-half contract.
No supply observer or guessed calibration table is enabled. There were no
parallel benchmark/test loads from the agent team during this window. CPU
affinity, host processes, GC and V8 tiering were not controlled.

## Observed results

Times are median milliseconds for one second of simulated audio. “Median ratio”
is baseline median divided by candidate median. “Paired median” is the median
of the six individual baseline/candidate ratios; the last column preserves their
range. These different statistics are not interchangeable.

| Clock | Firmware | Baseline ms | Candidate ms | Median ratio | Paired median | Paired min–max |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Physical | `rhythmic` | 1907.57 | 1519.08 | 1.256× | 1.185× | 1.054–1.536× |
| Physical | `lumiere-stereo` | 1807.42 | 1516.45 | 1.192× | 1.142× | 0.896–1.224× |
| Physical | `hq4-chego-auto` | 1813.19 | 1597.30 | 1.135× | 1.142× | 1.056–1.310× |
| Compatible | `rhythmic` | 1346.88 | 1116.45 | 1.206× | 1.216× | 1.100–1.305× |
| Compatible | `lumiere-stereo` | 1215.68 | 964.25 | 1.261× | 1.244× | 0.966–1.482× |
| Compatible | `hq4-chego-auto` | 1889.96 | 1608.94 | 1.175× | 1.122× | 1.044–1.404× |

Across **72 timed runs**, raw Float32 PCM bytes and full CPU diagnostics,
registers/I/O/SRAM, Flash, EEPROM and IRQ frames matched at every block endpoint;
remaining pin events matched after capture. Cross-trial determinism also passed.
There were 3384 checked endpoint snapshots across both clock passes. Separate
correctness fixtures cover physical OSCCAL/CLKPR phase changes, power/reset/NVM
mutations and scan-time faults; the focused test set passed **82/82** before
measurement. The benchmark does not retain every pin transition consumed by
native audio integration, so its trace claim is limited to the remaining ring.

The observed benefit supports retaining this conservative cache. Physical capture
still needs about 1.52–1.60 seconds per simulated second on this host. Further
work needs a new profile of this candidate; these totals do not identify an
exclusive timer/ADC/CPU cost or justify caching across time. The few trials and
overlapping ranges do not establish a universal speedup. Only the initial second
of these three excerpts was measured, and no browser/AudioWorklet timing was
tested.

## Reproduce

Run from the repository root, serially without other benchmark/test loads:

```powershell
node web-player/scripts/build-device-wasm.mjs --out-dir build/deadline-cache-test/runtime
node web-player/scripts/benchmark-deadline-cache.mjs --out build/benchmarks/deadline-cache-physical.json
node web-player/scripts/benchmark-deadline-cache.mjs --clock legacy --out build/benchmarks/deadline-cache-legacy.json
```

`--candidate`, `--baseline-ref`, `--frames`, `--rate`, `--trials`, repeatable
`--firmware` and `--out` are supported. Defaults match this report. The script
checks that only `device.c` differs in compiled inputs, so a later independent
native change requires selecting a matching baseline rather than silently
comparing different hardware models. The recorded cache source commit precedes
the benchmark script commit; the measured script itself is hashed in each report.

Raw JSON stays in ignored `build/benchmarks/`, including trial order, every run,
dispersion, checkpoints, host/runtime/source provenance and validation results.
The measured report SHA-256 values are
`53c2c82bc7b38ffaf17aebaa1fb81d3dac15ee61a3d49bea022302c639a24a70`
for `deadline-cache-physical.json` and
`68f41db218b8932be1b8e6e4b3a1abf6be06d20b407d28ef0d5b28eac2e0af6f`
for `deadline-cache-legacy.json`. The normalized measured script SHA-256 is
`fc9f90215fa6dab1350fdb201ad382e16f65853a2486ede3bd67194c2a3cbbf5`.
The shipped WASM and manifest are unchanged in these focused commits.
