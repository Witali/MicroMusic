# Bounded AVR control-flow regions

Retained as explicit `boundedRegions:true`, disabled by default. ATtiny13A/AVRe
physical HQ4 execution improved1.448x in the measured Node22/V8 workload.
Rhythmic/Lumière and CLKI/active-ADC controls do not establish a speed gain.
This closes a compiler experiment, not a full-device hardware checklist item.

## Implementation and correctness contract

`lib/avr-wasm-regions.js` finds cyclic strongly connected components of at most64
decoded words. Register-only ALU operations and direct RJMP/BRxx/SBRC/SBRS/CPSE
edges become WASM block/loop/br_table code. The emitted cases contain arithmetic
for already decoded instructions; no AVR opcode decoder runs inside the region.
Memory, I/O, stack, indirect flow, system operations and SREG bit changes use
the original callable instruction/basic-block paths.

A native event/deadline guard proves the worst-case cost of up to32 instructions
fits strictly before any observable boundary. The caller's instruction budget,
pending enabled IRQ, SEI/RETI delay, active continuation, f64 capacity, overflow
deadline and64-bit retirement headroom are preserved. CLKI retains its existing
zero region budget. Near events and partial deadlines use original phase code.

GPR values, SREG, PC and actual source cycle/count totals are staged in WASM
locals. The initial plan proposed lazy register loads; the implementation instead
preloads the statically used union once to avoid a validity branch on each read.
Only potentially written GPRs are flushed. Flushing an unchanged ordinary
register byte on a path that did not write it has no device-bus side effect.
Cached writes truncate to8 bits, signed ASR reads the current cached byte, and
register-pair accesses share the same cache. Every flag is maintained initially;
cross-block flag elimination is deliberately separate.

One native phase-clock call advances the exact actual path's original AVR cycles
while architectural registers still have their incoming values. Successful
completion commits staged registers/full SREG/PC and retirement exactly once.
Reset/fault and unexpected WAIT discard staged writes; a negative internal
result prevents basic-block replay of native work. Zero guard rejection can use
the unchanged block or instruction fallback. Device source edges and peripheral
events remain in the native scheduler. There are no added JavaScript callbacks.

The native runtime is unchanged:117901 bytes, SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.
Its two fixed memory pages and80-byte phase ABI are unchanged. Region locals
increase per-call temporary needs; no working-memory saving is claimed. Default
generation for all13 workloads is byte-identical to `bc8f6db`. Explicit runtime
settings enter cache identity and persist after SPM; an embedded package uses
its optional code until changed Flash is recompiled using runtime options.

## Validation and activation

All1673 Node tests passed with zero skips (92.07s). New checks cover all256
incoming SREG values, byte/pair aliases, cached ASR, external entries, short
instruction limits, every half-cycle and adjacent1ps deadline, bus exits and
two-word skips. They exercise IRQ/reset/protected EEPROM/WDT windows, CLKPR,
pending/delayed IRQs, active continuation, retirement headroom, oversized SCCs,
unequal CLKI transitions, host register edits, phase-local composition, isolated
package imports, package execution and held-clock SPM invalidation. A native
C/WASM probe verifies that the clock sees old GPR/SREG values at both ends of
the single span. All region-eligible forms from the official123-form fixture
also execute in real32-instruction batches against the individual-step oracle.
CLI generation/admission and physical package execution pass as well.
The region -> Binaryen133 Oz -> package pipeline separately preserves exact
PCM/full state/pins for1024 frames per real firmware (three packages,12
checkpoints with IRQs active). This untimed composition smoke test does not
extend the execution-speed claims to optimized packages.

The full13-workload validation matrix contains26 runs and168 exact PCM/full
architectural and diagnostic state/pin checkpoints. All default CPU bytes also
match the historical generator. An independent untimed prefix trace disables
idle acceleration and compares each equal-retirement endpoint with the original
runtime, without emitted instrumentation:

| Firmware, first1M instructions | Regions / words | Proven batches | Proven instructions | Checkpoints | IRQs |
| --- | ---: | ---: | ---: | ---: | ---: |
| rhythmic | 2 /38 | 4678 | 79740 | 3892 | 5497 |
| lumiere-stereo | 2 /38 | 3494 | 39630 | 3896 | 5543 |
| hq4-chego-tiny | 5 /26 | 17149 | 462093 | 3821 | 5712 |

The trace counts only returns that exceed the original basic-block length (or
positive returns at a non-block entry) and end inside that region. Other returns
are ambiguous; the counts are lower bounds, not whole-song coverage. All11609
prefix checkpoints preserve complete state and pin streams.

## Size and timing

Windows, AMD Ryzen5 5600X, Node v22.22.3/V8; unchanged Clang24/Binaryen133 native
runtime from the pinned Emscripten6.0.12 SDK. CPU binaries use the direct emitter
without the optional offline Binaryen pass. Each case uses eight balanced
four-label trials and four warmups per label: oldA/oldB identical raw CPU bytes,
newA/newB identical region bytes. Production translation cache reuse is asserted
within identity pairs, one native Module is shared, memories/instances are fresh,
and GC runs outside the timer. Construction, compilation and snapshots are
excluded. No profiling or tests run concurrently with these timings.

Three real-firmware cases capture12000 frames at48kHz with IRQs active; direct
kernels retire1M instructions. Other kernels capture1200 frames with explicit
20MHz clocks/divisor assertions. Every audio block/direct run compares exact
PCM, full state and pins. The two-case screen plus the remaining11-case matrix
contain416 timed runs,208 warmups and4032 exact checkpoints; they are disjoint
cases, not two independent replications of HQ4.

| Physical firmware CPU | Baseline bytes | Region bytes | Growth |
| --- | ---: | ---: | ---: |
| rhythmic | 387264 | 393723 | 1.67% |
| lumiere-stereo | 391150 | 397609 | 1.65% |
| hq4-chego-tiny | 406944 | 412470 | 1.36% |

| Workload | Median old/new | Paired range | Faster pairs /8 |
| --- | ---: | ---: | ---: |
| rhythmic compatible, identical bytes | 0.938x | 0.895–1.111 | 2 |
| rhythmic physical | 1.022x | 0.873–1.250 | 5 |
| lumiere compatible, identical bytes | 0.992x | 0.843–1.043 | 2 |
| lumiere physical | 1.018x | 0.918–1.109 | 6 |
| HQ4 compatible, identical bytes | 0.993x | 0.925–1.160 | 3 |
| HQ4 physical | **1.448x** | **1.213–1.595** | **8** |
| kernel compatible direct, identical bytes | 0.988x | 0.971–1.029 | 2 |
| kernel physical direct | **11.265x** | **10.934–11.724** | **8** |
| kernel CLKI20MHz /1 | 1.041x | 0.997–1.110 | 6 |
| kernel CLKI20MHz /256 | 1.011x | 0.983–1.057 | 5 |
| kernel internal20MHz /1 | **4.210x** | **4.032–4.303** | **8** |
| kernel internal20MHz /1, active ADC | 1.003x | 0.910–1.059 | 4 |
| kernel CLKI20MHz /1, active ADC | 1.006x | 0.987–1.126 | 6 |

The HQ4 median corresponds to about31% less measured execution time. Its gain
is consistent across all eight pairs; the old/new identity medians are1.005x/
0.976x, with raw ranges retained in JSON. Rhythmic/Lumière and event-heavy cases
show no reliable gain. The unchanged compatible rows quantify environmental
noise and cannot be interpreted as compiler regressions. The synthetic11.3x
result applies only to that event-free loop. This does not establish browser
speed, cold-start improvement, whole-song throughput or real-time audio without
underruns. Default engine and optional-feature defaults remain unchanged.

## Reproduce and continue

Exact sources and raw outputs are in [bounded-regions-20261025/](bounded-regions-20261025/).
The JSON source snapshot preserves the measured files, including the harness;
raw reports retain firmware hashes, alias resolution, CPU hashes, per-run times,
identity controls and parity digests. Reports were made from an uncommitted
candidate over `bc8f6db`; their `revision` records that base, while `sourceSha256`
identifies the measured implementation. HQ4 resolves to `hq4-chego-tiny`.
The retained implementation is `3561077`, CLI/API documentation `9f37e1f`,
and measurement tools `50b330e`. All measured source snapshots are byte-exact
after LF normalization against `50b330e`; the evidence verifier checks this.
Use that revision when reproducing the commands, with its bundled native WASM.

```sh
node web-player/reports/bounded-regions-20261025/verify-evidence.mjs
node web-player/reports/bounded-regions-20261025/verify-optimized-package.mjs
node web-player/scripts/benchmark-generated-wasm.mjs --transform bounded-regions --baseline-ref bc8f6db --validate-only --out build/bounded-validation.json
node web-player/scripts/trace-bounded-regions.mjs --out build/bounded-activation.json
node --expose-gc web-player/scripts/benchmark-generated-wasm.mjs --transform bounded-regions --baseline-ref bc8f6db --out build/bounded-timing.json
node --test web-player/tests/*.test.mjs tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
```

The last timing command covers all13 cases in one process; its measurements may
differ from the archived two invocations. Keep the native/source hashes fixed
and avoid concurrent work. Before enabling by default, test browser audio with
interrupts and actual buffer-underrun checks. Next candidates: a smaller adaptive
instruction budget near deadlines and per-region admission guided by measured
activation. Each needs separate parity and identity-controlled timing. Do not
combine them with cross-block flag elimination or peripheral timing changes.

Primary semantics: [Microchip AVR instruction encodings, flags and cycles](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny13A data sheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[WASM control/locals execution](https://webassembly.github.io/spec/core/exec/instructions.html)
and [WASM numeric semantics](https://webassembly.github.io/spec/core/exec/numerics.html).
Device addresses still come from the pinned official Microchip DFP3.4.278;
this experiment changes no vendor definitions or firmware source.
