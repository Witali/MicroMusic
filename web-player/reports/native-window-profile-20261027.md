# Separate native V8 samples by emulator work window

The diagnostic producer now has an explicit `--native-log-only` mode and timer
markers around each public capture/run. It never enables or starts the inspector
CPU profiler in that mode. Native ticks can therefore be assigned to a work
interior, a conservative boundary region or outside work. Production device
sources, native WASM, generated compiler identity and site defaults are unchanged.

The user's **10 ns** requirement applies to virtual events in the precise
verification simulator, as recorded separately in commit `643fd543`. It is not
a requirement for host sampling, marker clocks or the simplified site model.

## Why separate profiling modes

Two bounded local probes exposed an interaction in this Node/V8 version:

- Global `console.time` does not emit the required named native timer records.
  Documented `node:inspector` console timers do, with `--log-timer-events`.
- Inspector `Profiler.start` suppresses both these timer records and native
  `--prof` ticks. Moving markers outside the inspector session yielded only
  1, 1 and 0 native ticks in three roughly 1.2-second work intervals.

The new native-only mode retains an inspector Session solely for its console
timers, emits no `.cpuprofile`, and keeps the existing production-state/PCM
comparison. The ordinary inspector capture remains supported separately; an
actual default-mode control produces one valid 10-sample profile and its offline
audit reproduces every prior count. The inspector-tree auditor now explicitly
rejects native-only inputs instead of trying to read a nonexistent profile.

The earlier [whole-process source audit](native-source-profile-20261027.md)
remains valid as whole-process evidence. Its candidate source counts must not be
treated as samples from the inspector's measured work interval.

## Window contract and observations

Each generated safe numeric label has exactly one native start/end pair in the
same V8 clock domain as raw ticks. The host measures only `capture`/`run` with
`performance.now()`. Let `outerUs` be the marker interval and `innerUs` the host
work duration. The selected allowance at each end is:

```text
allowanceUs = ceil(max(0, outerUs - innerUs) + 2)
```

A tick is interior only strictly beyond both allowances. Other half-open outer
interval ticks remain boundary observations; every remaining tick stays outside.
This assumes a stable host-clock rate shared by the duration and V8 timestamps,
with a selected 2 µs rounding allowance. It is neither a universal clock bound
nor a host latency guarantee. Inconsistent durations reject. Zero/tiny windows
may have no interior. Logged ordering is preserved; clock rollback, nested or
overlapping windows, duplicate/missing/unknown reserved markers reject.

Three fresh physical direct-kernel runs each request 10,000,000 instructions at
nominal 20 MHz/D1. Constructors, reference runs and warmup remain outside markers.
The source map still requires exact production executable sections and absolute
offsets; all 218 function names/indices/body boundaries match the verified named
WASM. All runs preserve full architecture and PCM against production.

| Native tick view | All ticks | Project source candidates | Unresolved native | Other |
| --- | ---: | ---: | ---: | ---: |
| Interior | 227 | 70 | 122 | 35 |
| Boundary | 1 | 0 | 0 | 1 |
| Outside | 496 | 29 | 40 | 427 |
| Total | 724 | 99 | 162 | 463 |

| Run | Marker interval, µs | Measured work, µs | Allowance at each edge, µs | Interior ticks |
| --- | ---: | ---: | ---: | ---: |
| 0 | 1294244 | 1287331.0 | 6916 | 81 |
| 1 | 1184018 | 1183979.7 | 41 | 74 |
| 2 | 1153811 | 1153782.6 | 31 | 72 |

Adjacent whole-process raw tick gaps have median **15,812 µs**, despite the
native logger's requested 1000 µs interval. These observed gaps, logging,
disassembly and compilation effects prevent precise exclusive-duration claims.
Source-position predecessors and source maps remain candidate ownership, not
full C inline scopes. This experiment has no active-IRQ audio, underrun or
silicon-coverage claim. Stage 5 and the **24/31** checklist count remain open.

**61/61 focused tests pass:** 33 native parser/metadata/window tests and 28
existing profile attribution/function-name tests. Two additional CLI checks
reject the wrong audit mode and missing native window option without creating
an output. No runtime/library source changed; the earlier 2586 runtime/shared
checks were not repeated. [JSON evidence](native-window-profile-20261027.json)
pins sources, native inputs, raw capture inputs, mapping and test hashes.

## Replay

Create the capture directory, redirect the capture output to its `run.log`, and
retain the focused TAP as `build/native-window-profile-tests.log`:

```text
node --prof --log-timer-events --log-source-position --no-logfile-per-isolate --logfile=build/profiles/native-window-20261027/capture-native/v8.log --print-wasm-code web-player/scripts/profile-device.mjs --kernel --clock physical --operation direct --instructions 10000000 --frames 512 --repeats 3 --native-log-windows --native-log-only --out-dir build/profiles/native-window-20261027/capture-native
node --test web-player/tests/avr-v8-native-profile.test.mjs web-player/tests/avr-profile-attribution.test.mjs web-player/tests/avr-profile-functions.test.mjs
node web-player/scripts/audit-native-source-profile.mjs --input build/profiles/native-window-20261027/capture-native --out-dir build/profiles/native-window-20261027/map-native --python <configured-python> --test-tap build/native-window-profile-tests.log --output web-player/reports/native-window-profile-20261027.json
```

Original raw logs/disassembly stay in ignored `build/`. The retained report has
no native addresses, absolute host paths, marker start/end timestamps or embedded
source text. See the [cookbook contract](../../docs/avr-asm-cookbook/sampled-native-source-locations.md)
and the [Node inspector console API](https://nodejs.org/docs/latest-v22.x/api/inspector.html#inspectorconsole).
