# Automatic optimization of generated AVR CPU WASM

Optional offline optimization is implemented in both translation/package CLIs.
Default browser generation and the physical C runtime are unchanged. Binaryen
does not replace AVR-specific liveness or phase analysis. This experiment
supports a size-reduction option; it does not close the default-engine speed gate.

## Lowering and optimization boundaries

[`avr-transpiler.js`](../lib/avr-transpiler.js) decodes Flash independently,
emits a function for every word and guarded multi-instruction blocks, then
dispatch/capture functions. Registers use shared linear-memory bytes. Integer
operations become i32 arithmetic plus 8-bit truncation and required SREG logic.
The emitter already eliminates dead flags within a safe block. The phase emitter
adds temporary save/restore and stages around native clock barriers. Peripheral
imports bind directly to WASM exports, with no JavaScript opcode callbacks.
The [instruction mapping](../native/AVR_TO_WASM.md) records concrete examples.

Automatic passes can simplify arithmetic/control flow and temporary locals,
share repeated code and change function layout. The `Oz` rhythmic result has
more defined functions (572→624 ordinary, 571→622 physical), while its code
section shrinks sharply. Shared helper calls with constant parameters appear
in the disassembly. Smaller binary size does not imply fewer calls or faster
execution. Opaque device bridges remain effect boundaries. Cross-block SREG,
AVR constant propagation, larger direct-control regions and per-phase context
liveness still require translator-specific correctness analysis.

Native peripherals invoke Clang24 `-O3`. The prepared SDK's compiler driver
enables wasm-opt automatically: its help lists `--wasm-opt` as the default and
`--no-wasm-opt` as the override. The device build script does not invoke a
second separate pass. `profile-device.mjs` disables the driver's pass, then
reproduces it explicitly with names and checks every byte against production.
This experiment applies only to generated CPU modules. Browser engine compilation
remains a separate stage.

## Configuration and compatibility

Tool: `wasm-opt version133 (version_133-60-g93d6e9de7)`, from the local pinned
Emscripten6.0.12 SDK. Exact executable/input/output hashes are in every raw row.
Flags: `-O3` or `-Oz`, `--mvp-features`, `--enable-mutable-globals`,
`--skip-pass=remove-unused-module-elements`.

The ordinary default pipeline removed one required unused bridge import;
the physical pipeline removed five. Skipping that cleanup preserves the
existing package ABI rather than relaxing validation. Both import/export sets
and the embedded AVR manifest are checked. The existing package validator
also checks the complete bridge signatures, memory and dispatch-table geometry.
No trap, fast-math, zero-memory or closed-world assumptions are enabled.
Generated diagnostic function indices must not be reused after optimization.

## Results on this Node/V8 host

| Rhythmic CPU module | Raw bytes | Optimized bytes | Code-section bytes | Execution ratio |
| --- | ---: | ---: | ---: | ---: |
| Ordinary O3 | 172748 | 163777 | 119956→110988 | 1.033x |
| Ordinary Oz | 172748 | 94589 | 119956→41636 | 1.025x |
| Physical O3 | 387264 | 341596 | 334373→288708 | 0.996x |
| Physical Oz | 387264 | 115381 | 334373→62355 | 0.981x |

Ratios above one favor optimized CPU code. Eight balanced four-label trials
per row contain 128 timed runs, 64 discarded warmups and 2304 exact PCM,
state/diagnostic and pin checkpoints. The raw report preserves identity
controls and individual observations. Ordinary identity medians are
0.998/1.008 (O3), 1.000/0.998 (Oz); physical medians are 1.015/1.004 and
0.980/1.006. These data do not establish a physical-mode speed improvement.
The four completed timing rows are a two-workload screen, not the full
performance acceptance matrix or a browser benchmark.

A separate validation run checks all13 workloads with Oz: three actual firmware
images in both modes, two direct ALU kernels, 20MHz CLKI /1,/256, internal20MHz,
and internal/external active-ADC controls. Its26 runs retain168 exact checkpoints;
single runs are used for parity only, without speed inference. HQ4 requested
`hq4-chego-auto` resolves to actual `hq4-chego-tiny`; firmware hashes are pinned.
Across the three firmware images Oz reduces whole CPU modules by43–45% ordinary
and69–70% physical. The roughly50KB embedded manifest remains unchanged;
executable code-section reductions are larger than whole-file reductions.

Optimizer child-process observations are131–274ms for the four timing rows,
including process overhead, excluding generation and validation. These are
single observations, not browser startup costs. **The screen's `compileMs`
fields were measured after helper validation had already compiled both modules;
they are validation-warmed observations, despite the original harness's cold
wording.** The retained final harness calls them `compileAfterValidationMs`.
No cold-start or construction-time speedup is claimed.

New tests execute all123 official forms with O3/Oz, comparing complete
instruction effects and then actual unequal CLKI edges and adjacent1ps stops.
Package loading and the two CLIs are exercised. An optimized SPM regression
proves changed Flash is retranslated before the next fetch during a source hold.
Subsequent translations use the existing raw generator; no optimizer runs in
playback or synchronous SPM handling. Focused integration passed70 checks;
the full regression suite passed1641/1641 with zero skips (80.77s).

## Reproduction and evidence

```sh
node web-player/scripts/package-attiny13a.mjs pack firmware.hex optimized.json --optimize Oz
node web-player/scripts/benchmark-generated-wasm.mjs --case rhythmic-compatible --case rhythmic-physical --out build/benchmarks/generated-wasm-screen.json
node web-player/scripts/benchmark-generated-wasm.mjs --validate-only --level Oz --out build/benchmarks/generated-wasm-validation.json
node web-player/reports/generated-wasm-opt-20261025/verify-evidence.mjs
```

[Raw timing screen](generated-wasm-opt-20261025/screen.json),
[full validation matrix](generated-wasm-opt-20261025/validation.json), source
snapshots and full test output are retained alongside the verifier. The verifier
recomputes ratios, checks workload coverage and parity digests, source identities
and counts. The full device checklist remains21/30; hardware measurements,
Timer0 TOP=0, debugWIRE admission and default-engine acceptance remain open.

Primary sources: [Binaryen optimizer cookbook](https://github.com/WebAssembly/binaryen/wiki/Optimizer-Cookbook),
[pinned133 optimization flags](https://github.com/WebAssembly/binaryen/blob/version_133/src/tools/optimization-options.h),
[official WASM module/custom sections](https://webassembly.github.io/spec/core/binary/modules.html),
[AVR instruction manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf).
