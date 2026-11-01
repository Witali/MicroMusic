# Recover candidate C locations from V8 native samples

## Source-position labels through optimization, 2026-11-01

The [label-transport probe](../../web-player/scripts/probe-source-map-labels.py)
tests an additional route toward recovering inline ownership. It assigns
artificial IDs to input source positions using the `names` table and fifth
mapping field described by [ECMA-426](https://tc39.es/ecma426/). It leaves source
file, line and column intact. These IDs are not yet C inline-stack identities.

Using the already prepared full-debug pre-optimization runtime and source map,
run the registered SDK's optimizer with normal `-O3` and source-map input/output.
Use its directory in `$env:EMSDK`:

```powershell
python web-player/scripts/probe-source-map-labels.py --input build/profiles/native-current-20261030/kernel-map/runtime-debug-preopt.wasm --source-map build/profiles/native-current-20261030/kernel-map/preopt.map --emsdk "$env:EMSDK" --out-dir build/experiments/source-map-labels-20261101
python web-player/tests/source-map-labels.test.py
```

The probe checks every non-custom WASM section's bytes **and start offset**
against production. This matters because adding a custom section before code
can preserve instructions while invalidating sampled module offsets. Every
emitted label must resolve back to its exact original file/line/column. Unknown
or mismatched labels fail. The probe refuses to run with Python `-O`.

The [retained result](../../web-player/reports/source-map-labels-20261101.json)
pins the preopt/map, optimizer, output and script hashes. On Emscripten 6.0.12,
Binaryen 133 (`version_133-60-g93d6e9de7`), all three variants preserve executable
sections and offsets:

| Variant | Mapped output positions | Named positions | Distinct labels |
| --- | ---: | ---: | ---: |
| Original map | 14965 | 0 | 0 |
| One shared label | 14965 | 14965 | 1 |
| One label per input position | 15696 | 15696 | 13935 |

There are 15105 labeled input positions. Missing IDs remain absent; transformations
can also duplicate a source position. Metadata boundaries differ even though
the executable bytes are identical, so these counts are not instruction counts,
CPU cost or a speedup. Six contract tests cover unmapped gaps, duplicate source
positions, incorrect/unknown origins, malformed VLQ/maps, custom-section offset
shifts and disabled assertions. Raw maps/binaries remain in ignored `build/`.

Next extract actual inline DIE/range stacks from the preopt DWARF, attach their
IDs through this verified channel, and reapply code/offset and origin checks
before joining them with native sample PCs. No inline scopes or exclusive
durations have been assigned by this probe. The production runtime, compiler
identity and seven open hardware/performance plan items remain unchanged.

## Existing native-sample reconstruction

Target: the ATtiny13A full-device WASM runtime on the recorded Windows x64,
Node 22.22.3/V8 12.4.254.21-node.56, Clang 24/Binaryen 133 SDK configuration.
This is diagnostic tooling for the open cost-attribution task. It changes no
production CPU/peripheral ABI, native artifact, compiler identity or engine
default. It adds no instruction/clock-edge JavaScript callback.

The inspector CPU profile identifies surviving WASM functions. Its function
location is an entry offset, and its line ticks do not provide instruction PCs
inside a function. A DWARF lookup at that entry cannot recover the source owner
of code inlined into a mixed scheduler function.

The [V8 sampling-profiler documentation](https://v8.dev/docs/profile) describes
`--prof`. The local engine also exposes `--print-wasm-code`; its
[WasmCode disassembler implementation](https://chromium.googlesource.com/v8/v8/+/f67aa5ca18a419c5ea1a9613d8b3555bd056305d/src/wasm/wasm-code-manager.cc)
prints native code ranges and source-position tables. That upstream revision is
a format reference, not a claim that it is the exact local engine revision.
The retained capture proves the actual local format used by this tool.

The diagnostic path is:

1. Record raw tick leaf PCs, native code creation records and disassembly in
   the same process. Never combine address ranges from separate processes.
2. Match the native code generation, expected function name/index and metadata
   offsets. Ties, multiple generations and missing ranges remain unresolved;
   unsupported code-move/delete records reject the audit.
3. Find the preceding native source position within that function. The printed
   native offset is hexadecimal; its WASM position is decimal and relative to
   the function body. Add the verified body offset before looking up the map.
4. Resolve the resulting module byte offset through a single-line V3 source
   map. Retain unmapped spans instead of carrying a source across them or
   across a function boundary.

Generate the map from the original pinned inputs. Compile with the production
flags plus `--no-wasm-opt -g`, then run the prepared SDK's original
`wasm-sourcemap.py`. Feed that map to normal `wasm-opt -O3` with
`--input-source-map` and `--output-source-map`. Require **all executable sections
and their absolute byte offsets** to match production before using the result.
The auxiliary output's debug/custom sections are not executed or shipped.

Keeping `-g` through Binaryen optimization was rejected in this experiment:
its executable sections differ from production. The
[Emscripten debugging documentation](https://emscripten.org/docs/porting/Debugging.html)
explains that retained DWARF can inhibit optimization, while source maps can
survive post-link optimization. Equality still needs an actual check for each
toolchain/input version; it is not a general property of debug builds.

[The pure parser](../../web-player/scripts/lib/avr-v8-native-profile.mjs) validates
the log, disassembly, ranges and VLQ mappings. It exports disjoint observation
counts and normalized project source/line labels, with no raw native addresses
or host paths. External source paths count as support; they are not published.
[The replay command](../../web-player/scripts/audit-native-source-profile.mjs)
checks current native inputs, capture identity, exact code/offset parity,
the complete function-name/index/body-boundary mapping against the named WASM,
registered source files and line bounds, then pins input/tool/source hashes.

This resolves **candidate sampled source locations**, not precise exclusive
subsystem durations. Source-position predecessors can cover intervening native
instructions, source maps lack full C inline scopes, optimization can merge
work, and sampling does not show ownership between samples. Whole-process ticks
also include setup/reference/warmup and generated CPU/VM work. No speedup,
underrun rate or hardware coverage follows from these counts.
Disassembly output, logging, compilation and the profilers also perturb the
captured process; these observations are not uninstrumented execution timings.

The [retained experiment](../../web-player/reports/native-source-profile-20261027.md)
records the workload, completed tests, resolved and unresolved budgets. A future
cost producer still needs ambiguity/error bounds and overhead controls before
closing the plan's exclusive-timing item. The subsequent
[window experiment](../../web-player/reports/native-window-profile-20261027.md)
adds validated work markers without claiming exclusive durations.

## Native work markers

Use `--native-log-windows --native-log-only` with Node `--prof --log-timer-events`
to delimit raw native samples. The documented
[inspector console](https://nodejs.org/docs/latest-v22.x/api/inspector.html#inspectorconsole)
provides `time`/`timeEnd` in the tested engine. Node's global console does not
emit those named native records. Do not start the inspector CPU profiler in
this mode: the observed engine suppresses native timer events and ticks while
that profiler runs. Keep inspector-tree and native-log captures separate.

The native timer interval encloses the measured public operation. Conservative
edge classification uses its excess over the host work duration plus a selected
2 µs rounding allowance at each edge. This assumes stable host-clock rate
correspondence; it is not a universal precision guarantee. Every tick remains
in exactly one interior/boundary/outside view. Validate logged chronology,
including backwards clocks, rather than sorting away malformed event order.
Empty interiors stay empty. The project's verification-only 10 ns virtual-event
tolerance does not apply to these host measurements.

## Preserve known function containers across source-map gaps

Missing source positions do not always mean that the surrounding compiled
function is unknown. Keep a separate `nativeFunctions` table in every whole,
interior, boundary and outside view. Its numeric indices refer to the complete
function metadata validated against the captured named WASM; the diagnostic
output never copies function names, native addresses or host paths.

Assign a container only when a tick has one earlier, non-tied code generation,
one matching disassembly block and an offset in the printed instruction range
`[0, instruction_size)`. Do not extend that range to the allocation size:
the referenced V8 disassembler excludes padding and non-instruction tables.
Missing/ambiguous disassembly, creation ties, overlapping generations and
allocation padding remain uncontained. A prologue inside the instruction range
can have a known container while its source owner remains unresolved.

Each row retains the existing project/support/unresolved source budget and
unresolved reasons. Check both row totals and the global identity:

```text
sum(nativeFunctions.ticks) + uncontainedNativeTicks
  = project + support + unresolvedNative
```

The `other` budget includes generated CPU/VM/unknown code outside the recognized
native-runtime generations; it is not silently assigned a native container.
Multiple disjoint compiled generations can share the same verified function
index. Work-window partitions must conserve every function's category counts
and unresolved reasons as well as the global source budget.

This records where a sampled PC lies. It cannot assign inlined scheduler work
to a peripheral, convert sparse samples into exclusive durations or prove an
execution-speed improvement. Keep the source-map gaps and the existing host
clock/marker assumptions explicit. See the
[offline replay evidence](../../web-player/reports/native-function-containers-20261030.md).

## Recheck priorities after changing native arithmetic

The [current capture](../../web-player/reports/native-current-profile-20261030.md)
rebuilds maps against the exact post-optimization native bytes and extends the
kernel to 100 million instructions and music to 262144 stereo frames. Phase
handling and `next_event_scan` are the next investigation candidates; counts
remain sampled containers, not exclusive subsystem costs. Different workloads,
versions and capture lengths do not form an old/new timing comparison.

Before pruning dominated deadlines, preserve conversion faults as well as the
minimum timestamp. `min(at_half(a),at_half(b))` is not generally interchangeable
with `at_half(min(a,b))`: converting the later candidate can fail even when the
earlier one fits. Prove every skipped candidate's representability, or retain
its fault check. This is a source-review constraint, not an implemented or
benchmarked optimization. Start with scan/conversion counts and invalidation
causes; a smaller helper-call count alone does not establish speed.
