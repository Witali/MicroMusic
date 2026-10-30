# Preserve native function identity across missing source positions

Offline replay now retains a verified function container for native samples
whose C source location remains unresolved. Every whole-process and work-window
view contains numeric function indices, source-category budgets and unresolved
reasons. Raw names, addresses and host paths are omitted. This is diagnostic
progress on the open profiling task; production sources, native WASM, generated
compiler identity, timing and site behavior are unchanged.

## Validation and unchanged evidence

The input is the completed 2026-10-27 capture from
[the native work-window experiment](native-window-profile-20261027.md): three
10,000,000-instruction physical direct-kernel runs at nominal 20 MHz/D1. This is
an offline reanalysis, not another performance run or an active-IRQ audio test.

The producer validates all 218 function names/indices/body ranges against the
actual named WASM. It rebuilds the source map and requires executable sections
and absolute section offsets to equal production. The native artifact remains
124,505 bytes, SHA-256
`ad3e472582cbca5f7d0d57b7b17776c58a03f9b5f7eb89b55fda89ea84389fc7`.

Independent comparison with the retained prior JSON verifies that native
identity, native inputs, all five raw capture hashes, mapping identity, tick gaps
and every prior source classification/count/window field are unchanged. Only
the new function summaries and explanatory limits are added to the audit.

**68/68 focused tests pass:** 40 native metadata/parser/window checks and 28
existing attribution/function-name checks. New cases distinguish true prologue
instructions from allocation padding, retain missing-map/position uncertainty,
reject ambiguous/tied/missing-disassembly containment, aggregate disjoint tier
generations, preserve numeric-only output and conserve per-function budgets
through all window partitions. The earlier runtime-wide suite was not repeated
for this diagnostic-only change.

## What the replay establishes

| View | All ticks | Known native function range | Uncontained recognized native | Other |
| --- | ---: | ---: | ---: | ---: |
| Interior | 227 | 192 | 0 | 35 |
| Boundary | 1 | 0 | 0 | 1 |
| Outside | 496 | 69 | 0 | 427 |
| Whole process | 724 | 261 | 0 | 463 |

All 162 whole-process source-unresolved native observations, including 122
interior observations, lie inside verified instruction ranges. They retain
their original unresolved source categories. The whole-process native budget
is still 99 project source candidates plus 162 source-unresolved ticks. The
32 observed function indices account for all 261 recognized native ticks.
Generated CPU, VM and unknown observations remain in `other`.

The most frequently observed native containers inside the work windows are:

| Verified index | Symbol in pinned native metadata | Ticks | Project source candidate | Source unresolved |
| --- | --- | ---: | ---: | ---: |
| 155 | `ratio` | 37 | 1 | 36 |
| 49 | `avr_device_phase_clock` | 17 | 14 | 3 |
| 165 | `next_event_scan` | 15 | 12 | 3 |
| 142 | `analog_comparator_advance` | 11 | 0 | 11 |
| 148 | `mirror` | 11 | 6 | 5 |

The three separate interiors have 81/74/72 ticks, of which 62/66/64 are in
recognized native functions. `ratio` has 18/11/8 observations respectively.
These are sparse counts from one retained kernel configuration. They do not
establish percentages of elapsed time or predict another firmware's costs.

## Containment and next step

Require one earlier non-tied code generation, one matching disassembly and a PC
inside its printed half-open instruction range. Do not use allocation size:
the referenced [V8 disassembler](https://chromium.googlesource.com/v8/v8/+/f67aa5ca18a419c5ea1a9613d8b3555bd056305d/src/wasm/wasm-code-manager.cc)
separates instructions from padding and non-instruction tables. Missing or
ambiguous ranges stay uncontained. The linked upstream revision documents the
format, not the exact local V8 revision; the actual retained log/disassembly
establishes the tested local format.

The next bounded performance investigation can inspect `ratio`'s actual native
instructions and call-site invariants. It must distinguish source-unmapped
prologue work from arithmetic before choosing a new experiment. Previously
rejected equal-rate and bounded-multiply guards remain rejected; these counts
do not justify restoring them. Use real-firmware and active ADC/watchdog/CLKI
controls and balanced uninstrumented measurements before retaining a change.

Function containment cannot split C code inlined into a scheduler function by
subsystem. Existing source-map, sparse-sampling and host-marker clock limits
remain. No exclusive CPU/peripheral/pin duration, speedup, real-time audio or
silicon claim follows. The plan remains **24/31 complete, seven open**; the
verification-only 10 ns virtual-event contract is unchanged.

## Replay

With the original ignored capture retained locally:

```text
node --test web-player/tests/avr-v8-native-profile.test.mjs web-player/tests/avr-profile-attribution.test.mjs web-player/tests/avr-profile-functions.test.mjs
node web-player/scripts/audit-native-source-profile.mjs --input build/profiles/native-window-20261027/capture-native --out-dir build/profiles/native-function-containers-20261030 --python <configured-python> --test-tap build/native-function-containers-tests.log --output web-player/reports/native-function-containers-20261030.json
```

Redirect the first command's TAP to `build/native-function-containers-tests.log`.
[JSON evidence](native-function-containers-20261030.json) pins sources, raw input
hashes, exact native/map identity and passing TAP. The
[cookbook](../../docs/avr-asm-cookbook/sampled-native-source-locations.md#preserve-known-function-containers-across-source-map-gaps)
records the reusable containment and conservation rules. No new external
download was needed.
