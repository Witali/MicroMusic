# Full-device sampling profile, 2026-10-23

The strongest repeated hotspot is native scheduler/deadline work, especially
`device.c:next_event`. This profile supports prioritizing deadline reuse and
same-time peripheral work before further AVR arithmetic lowering. It does not
provide exact exclusive CPU/peripheral wall times.

## Reproduction

```powershell
node web-player/scripts/profile-device.mjs --out-dir build/profiles/device-20261023
```

Defaults: `rhythmic`, `lumiere-stereo`, `hq4-chego-auto`, 48,000 frames at 48 kHz,
three profiles per firmware, 1024-frame capture calls, `fastIdle:true` and
`optimizeFlags:true`, requested sampling interval 1000 microseconds. Options:
`--frames`, `--rate`, `--repeats`, `--interval-us`, repeated/comma-separated
`--firmware`, `--out-dir` and `--emsdk`. The prepared Emscripten 6.0.12 SDK is
located automatically under an ancestor's `build/toolchains/`, or supplied with
`--emsdk`. It is read without modification.

The script produces raw `.cpuprofile` files, a detailed `summary.json`, optimized
native and generated-CPU function maps and diagnostic WASM, all under ignored
`build/`. These bulky diagnostics are intentionally not committed. The raw
profiles can be loaded into DevTools' JavaScript CPU profile viewer.

The run was sequential, with no parallel benchmark launched by this agent. Each
firmware first ran once with production modules to obtain a reference, then once
with named modules as warmup, outside the profile. Every measured repeat used a
fresh device and the same interval from reset. Construction, lowering, compiling,
hashing, output concatenation and validation occurred outside the capture window.
No DSP was run in this profile; `capturePhysical` includes native physical-pin
integration and wrapper copies. No instruction/event JavaScript callback or
production instrumentation was added.

Every named/profiled run matched the production reference byte for byte for raw
Float32 PCM, full visible data/Flash/EEPROM, final public state and IRQ frames.
All nine checks passed. This comparison checks diagnostic equivalence for these
inputs, not hardware fidelity.

## Names and executable identity

This SDK's Clang driver automatically invokes `wasm-opt -O3` after linking. The
linker's map therefore has pre-optimization indices and cannot directly name
production functions. Adding Clang `-g` also does not preserve the final names.

The script uses the original manifest flags, adding `--no-wasm-opt` and a linker
map. It then explicitly runs the same `wasm-opt -O3` with `--print-function-map`.
The resulting WASM must match **every production byte** before the script accepts
its final function index/name map. The linker map supplies only source-object
ownership. This run resolved all 117 optimized native functions. Source functions
that were inlined have no independent surviving frame.

A diagnostic `name` custom section is appended to the original production bytes,
prefixing names with `native.<source-object>.`. Generated CPU names come from its
existing import count, 512 instruction-body order, block metadata and exports;
they use `cpu.insn_0x...`, `cpu.block_0x...` and driver names. All non-custom
sections are verified unchanged in each named module. These custom sections are
metadata under the [WebAssembly name-section specification](https://webassembly.github.io/spec/core/appendix/custom.html#name-section).

Relevant native function indices for this exact runtime:

| Index | Name |
| ---: | --- |
| 20 | `native.avr.full_clock` |
| 47 | `native.avr.full_audio_collect` |
| 87 | `native.device.mirror` |
| 89 | `native.device.elapse` |
| 90 | `native.device.advance_to` |
| 91 | `native.device.next_event` |
| 103 | `native.timer0.event_distance` |
| 116 | `native.support.__multi3` |

## Observations

Host: Windows x64, AMD Ryzen 5 5600X, Node 22.22.3. The source base was merge
`96c6183227ac5b19e0505baad49e9bafacff07c3`, incorporating root through `9b1b208`.
The profiling script was untracked at capture time; its normalized-LF SHA-256 was
`d132ec345bfa695f6fb42c4b59c1050597c20e6256390998ef9ec57273a5d3ef`.
Runtime SHA-256:
`ff1f8203977328de99e20eb41a396b331ffb8c1ce886cf2d7e5be0caadc079d9`.
Detailed summary SHA-256:
`00a2b4d42636c9edb686cc1bdabcfdb6c44a4d1daa435b6b3b2f4d41aedb40ca`.
The summary also retains all relevant normalized source hashes, compiler flags,
Node/V8 versions, module hashes and individual raw-profile hashes.

| Firmware | Profiled capture wall ms, repeats 0/1/2 | All samples | Samples with capture ancestry |
| --- | --- | ---: | ---: |
| rhythmic | 1245.44 / 1211.89 / 1228.47 | 2364 | 2358 |
| lumiere-stereo | 1107.23 / 1084.23 / 1085.98 | 2107 | 2100 |
| hq4-chego-auto | 1630.11 / 1663.57 / 1655.56 | 3182 | 3176 |

The following percentages are counts pooled across repeats, divided by samples
whose recorded ancestor stack includes public `capturePhysical` in
`attiny13a-runtime.js`. They count the observed **leaf frame**. Categories describe
the surviving function's source ownership; inlined work stays attributed to its
container. Thus “board body” can include inlined peripheral work, and “bridge
body” can include clock/deadline checks or audio work. They are not exact
exclusive subsystem costs.

| Observed leaf-frame ownership | Music % | Stereo % | Speech % |
| --- | ---: | ---: | ---: |
| Native board/scheduler bodies | 46.01 | 45.05 | 47.73 |
| Generated CPU bodies/drivers | 15.01 | 14.76 | 14.14 |
| Native analog bodies | 11.79 | 12.43 | 10.58 |
| Native bridge bodies | 9.84 | 10.57 | 10.58 |
| Native Timer0 bodies | 7.17 | 7.81 | 8.19 |
| Native audio integration bodies | 4.83 | 4.29 | 3.68 |
| Native arithmetic support | 3.77 | 3.71 | 3.46 |
| Native other peripheral bodies | 1.06 | 0.57 | 0.91 |
| Native GPIO bodies | 0.30 | 0.52 | 0.54 |
| Native pin propagation bodies | 0.08 | 0.24 | 0.06 |
| JavaScript bridge | 0.13 | 0.05 | 0.13 |

The very small JavaScript leaf counts do not establish a zero bridge cost, but
they do not indicate JavaScript instruction callbacks as the dominant hotspot in
this sampled physical path.

| Function | Music leaf / inclusive % | Stereo leaf / inclusive % | Speech leaf / inclusive % |
| --- | ---: | ---: | ---: |
| `next_event` | 19.47 / 25.83 | 20.76 / 26.62 | 20.37 / 26.73 |
| `advance_to` | 10.39 / 55.89 | 10.38 / 55.71 | 10.20 / 57.08 |
| `elapse` | 6.28 / 6.62 | 5.48 / 6.00 | 6.20 / 6.55 |
| `full_clock` | 5.30 / 78.07 | 5.76 / 77.57 | 6.23 / 80.01 |
| `full_audio_collect` | 4.83 / 5.17 | 4.24 / 4.67 | 3.62 / 3.72 |
| Timer0 `event_distance` | 4.03 / 4.03 | 3.86 / 3.86 | 5.01 / 5.01 |
| `mirror` | 2.84 / 2.84 | 2.67 / 2.67 | 4.09 / 4.09 |

Inclusive counts overlap: `full_clock` includes scheduler, analog, timer and audio
descendants. Its roughly 80% inclusive observation must not be called 80%
exclusive bridge/clock cost or added to `advance_to`'s roughly 56% inclusive count.

## Source-backed next experiments

1. **Reuse absolute deadlines with explicit invalidation.** `advance_to` calls
   `next_event` at the loop head and again at an endpoint. After a CPU clock,
   `full_clock` calls `full_deadline`, which reaches `device_next_cpu_event` and
   scans again. `next_event` asks every peripheral for its deadline and performs
   base/CPU/wall-clock conversions. Cache an absolute base-half deadline, preserving
   events at exactly the current timestamp, with mutation/event invalidation.
   This targets the largest repeated leaf observation. Correctness requires a
   complete mutation map; an unbounded stale cache is unsafe.
2. **Avoid duplicate same-time analog advancement.** `service` calls
   `analog_advance`, then `sources` calls `analog_sources`, which calls
   `analog_advance` again. `connect_sources` reaches another ADC advancement at
   the same timestamp. Advance and trigger evaluation need distinct dirty/time
   guards so a changed comparator/source flag is still delivered at that time.
   The 10.6–12.4% analog-body observations make this worth an isolated prototype.
3. **Batch physical audio collection to a safe deadline.** `full_clock` calls
   `full_audio_collect` after every CPU clock barrier while capture is active.
   A bounded ring-pressure deadline plus audio sample deadline could reduce
   repeated polling and deadline division. Preserve exact pin edge timestamps,
   future events beyond the sample boundary, and bounded ring occupancy; do not
   simply postpone every drain until the end of a large block.
4. **Reduce repeated wall-time/deadline arithmetic after caching.** `__multi3`
   accounts for 3.5–3.8% of leaf observations, with recorded parents predominantly
   `next_event`, plus `elapse` and `full_clock`. Preserve overflow checks and
   rational remainders. First remove redundant conversions/calls; then consider a
   proven bounded-delta fast path with the current general fallback.
5. **Evaluate dirty I/O mirrors after those changes.** `mirror` rewrites all
   modeled I/O bytes at service boundaries. Its 2.7–4.1% leaf observations suggest
   a later candidate, with strict visibility at IN/LDS, writes, IRQ entry and
   public state snapshots.

These are source-based hypotheses for controlled experiments, not measured
speedup predictions. No production optimization was made in this change.

## Sampling limits

The script follows the [Node CPU profiler API](https://nodejs.org/download/release/v22.22.3/docs/api/inspector.html#cpu-profiler).
The [V8 profiler protocol](https://chromedevtools.github.io/devtools-protocol/tot/Profiler/)
defines sample-node IDs and time deltas. This report uses sample counts, not
inclusive counts converted into milliseconds. Despite a requested 1000-us
interval, observed per-profile median deltas were 1547–1557 us and maximum gaps
20.3–31.7 ms. Sparse, interrupted or biased samples can miss short work.

V8/LLVM inlining, profiling overhead, compiler tiering and sample-stack visibility
limit attribution. GC/VM samples can lose capture ancestry; all-profile categories
are retained separately instead of silently reassigning them to a subsystem.
There is no CPU affinity, forced GC, fixed clock or whole-host isolation. This is
one Node host and the first emulated second, not browser AudioWorklet latency or
a controlled comparison with the previous benchmark run. Exact exclusive costs,
call counts and a causal optimization gain require further instrumentation or
paired experiments.
