# Sampling the adaptive bounded-region path

Source: clean `298a9b6f2d483a55c9a4f53a4ef52e86284508ce`, after main integration.
Node 22.22.3 / V8 12.4, Windows x64, Ryzen 5600X; Clang 24 / Binaryen 133.
Native runtime: **118,969 bytes**, SHA-256
`9f1eefa094f9003419251408953309e3b3c4050fc217234b9b95ed0275d87778`.
No production CPU/native source or artifact changes accompany this study.

The optional adaptive budget policy is enabled (`boundedRegions:true`), with
phase-local liveness disabled. This answers the saved plan's request for a fresh
profile after the budget change. It is not an old/new timing comparison: main
also changed the native binary since the prior post-GPIO study.

## Diagnostic correctness

The previous profiler did not expose the region option and could call every
extra nonexported function `cpu.emptyBlock`. It also assumed 512 Flash words.
The updated helper derives counts from the manifest and separately names region
bodies, entry wrappers and wrappers with ordinary-block fallbacks. It checks
unique diagnostic names, consecutive indices, body count and actual export
indices. Six tests inspect real emitted binaries, including their element-table
dispatch targets, both phase-local settings, bad metadata and ATtiny88 geometry.

Native symbols come from a byte-identical optimized rebuild. Both CPU and native
diagnostic binaries add only custom name sections; executable bytes are identical
to the corresponding production modules. The capture windows contain no source
counters or per-instruction JS hooks. Construction, comparison and serialization
are outside them. All 90 library/native/tool/catalog source identities are pinned.

All 15 named/profiled runs match their uninstrumented production reference on
raw PCM, full public/diagnostic CPU state, data memory, Flash/EEPROM, IRQ frames
and retained tail pin events. The frozen replay independently reconstructs the
function names and every raw-profile self/inclusive count and percentage. Its
optional execution check reruns all five archived CPU cases against the original
native binary and matches the complete observation and PCM hashes.

## Workloads and observations

Three fresh profiles per case; 48 kHz output, 1024-frame host blocks, requested
sampling interval 1000 µs. Real firmware uses 48,000 frames, physical 9.6 MHz,
active Timer0/IRQs and the existing benchmark input/analog events. HQ4 resolves
`hq4-chego-auto` to `hq4-chego-tiny`. The 20-MHz internal kernel uses 480,000
frames; external CLKI uses 4,800 frames with exact 25,000-ps high/low phases.
Both kernels explicitly set CLKPR to /1. The short internal pilot (34 work
samples) was superseded by this longer interval and is not pooled.

The retained **15 profiles / 14,031 work-stack samples** give:

| Case | Work samples | Phase-clock inclusive | Event scanner self | Ratio self | Duration self | Mirror self |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rhythmic | 3267 | 70.62% | 9.58% | 5.69% | 5.33% | 6.37% |
| Lumière stereo | 3353 | 71.55% | 9.16% | 5.73% | 5.28% | 6.29% |
| HQ4 | 1464 | 69.88% | 8.54% | 5.33% | 4.71% | 6.22% |
| Internal kernel, 10 s virtual | 3739 | 60.90% | 5.86% | 7.38% | 2.92% | 5.05% |
| CLKI kernel, 0.1 s virtual | 2208 | 88.54% | 8.33% | 2.22% | no leaf sample | 5.43% |

These are surviving-frame observations: inclusive counts overlap; O3/V8 inlining
attributes work to its containing body. They do not isolate peripheral time or
prove speed changes. Different workload lengths must not be compared as elapsed
throughput. All raw deltas and gaps are preserved; the requested interval is not
guaranteed.

Real region frames are now distinguishable. Rhythmic/Lumière's single regions
appear in 1.22%/1.04% of work stacks. HQ4's leading region `0x003c` appears in
7.04%, with three other regions also observed. In the internal kernel, its region
has 16.50% self / 67.10% inclusive samples; those inclusive samples include its
native clock descendants. No distinct region body/entry/fallback frame was
sampled in CLKI. That is consistent with its zero positive native batch budget;
sampling is not an execution-count proof.

## Next action and limits

The data keeps native clock/scheduler work ahead of another register-only region
experiment. Audit the ownership of `full_deadline()` and event-to-cycle/time
conversion across one CPU barrier before changing it. In particular, determine
whether a proven event-free span can reuse derived deadlines without rounding
up across a physical endpoint, stale IRQ/reset/ADC/EEPROM/watchdog state, or
changing the canonical bus/public-exit view. This is an unimplemented hypothesis.
Keep any experiment separate from the rejected scoped I/O publication and
small-product clock guards. Its acceptance still needs balanced uninstrumented
music/internal/CLKI/active-ADC controls and exact phase/buffer observations.

No real-time browser gate or hardware ambiguity closes. Default remains `wasm`;
the main checklist remains **21/30**, nine open. This run adds no claim about
browser underruns, silicon phase behavior, exclusive subsystem cost or speedup.

## Reproduction

```
node --test web-player/tests/avr-profile-functions.test.mjs
node web-player/reports/bounded-profile-20261026/replay.mjs
node web-player/reports/bounded-profile-20261026/replay.mjs --verify-execution
node web-player/scripts/profile-device.mjs --clock physical --bounded-regions --benchmark-controls --frames 48000 --repeats 3 --out-dir build/profiles/bounded-current-music
node web-player/scripts/profile-device.mjs --kernel --clock physical --bounded-regions --benchmark-controls --frequency 20000000 --frames 480000 --repeats 3 --out-dir build/profiles/bounded-current-internal-long
node web-player/scripts/profile-device.mjs --kernel --clock clki --bounded-regions --benchmark-controls --frequency 20000000 --frames 4800 --repeats 3 --out-dir build/profiles/bounded-current-clki
node web-player/scripts/analyze-device-profiles.mjs --without-calls --input build/profiles/bounded-current-music --input build/profiles/bounded-current-internal-long --input build/profiles/bounded-current-clki --out-dir build/profiles/bounded-current-analysis
```

Run profiling sequentially with other project tests/timings stopped. The frozen
[evidence](bounded-profile-20261026/evidence.json) retains all raw profiles,
summaries, CPU/native name maps and binaries, tool/test sources and test output.
Static replay uses the pinned Git sources. Execution replay additionally requires
matching current library sources; future code should use that source revision.
