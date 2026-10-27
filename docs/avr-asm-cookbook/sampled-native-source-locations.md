# Recover candidate C locations from V8 native samples

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
cost producer still needs independently delimited work windows, ambiguity/error
bounds and overhead controls before closing the plan's exclusive-timing item.
