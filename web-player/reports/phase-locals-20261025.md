# Per-phase temporary liveness

Implemented as explicit `optimizePhaseLocals:true` for resumable ATtiny13A
translation. The default full-context path remains the oracle. This is a
measured code-size improvement, not an accepted execution-speed improvement.
Native runtime SHA-256 remains
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.

## Algorithm and correctness boundary

`avr-phase-locals.js` adds generation-time local-read, local-write and branch
annotations to the existing emitter. Backward liveness unions branch inputs;
a write kills an old value only on every path that could need it. Ignoring
early returns is conservative. The suspended phase's clock expression must
also be live because it is evaluated again when execution resumes. Annotations
are stripped before serialization; no bytecode parser or instruction interpreter
is introduced. Clock markers remain top-level and cannot enter nested control.

Each WAIT stores only its live local mask. Resume restores the corresponding
mask according to the saved stage. The nine i32 plus one f64 temporary layout and80-byte
native context allocation are unchanged; unused slots are unspecified scratch.
Native C does not read these temporary slots: it exports their layout and
manages phase/clock/retirement state. AVR registers, SREG, SRAM, bus effects,
half phases and event timestamps retain their existing contract. No source edge,
peripheral event or JavaScript boundary is removed. No AVR assembly is added.

The option enters translation-cache identity and is checked even when a
precompiled module is supplied. Explicit runtime settings persist after SPM.
Original instructions and register-only blocks remain separately emitted;
annotations are stripped before block-local index remapping as well.

## Code size

Baseline generator: `c8cf6bd`. The harness loads the original translator and
phase emitter directly from Git, redirecting only their import URLs to the
unchanged device profiles and historical phase source. All13 default outputs
are byte-identical to that baseline; the report retains source hashes.

| Physical firmware CPU | Full bytes | Live bytes | Full/live code section | Static full/live slots |
| --- | ---: | ---: | ---: | ---: |
| rhythmic | 387264 | 294931 | 334373 / 241947 | 9320 / 1506 |
| lumiere-stereo | 391150 | 298249 | 338039 / 245045 | 9440 / 1520 |
| hq4-chego-tiny | 406944 | 310022 | 352935 / 255918 | 10230 / 1620 |

Whole physical modules shrink23.8–23.9%. Slots count syntactically emitted
WAIT sites across every Flash word, including fault/unreachable bodies; they
are not dynamic spill counts or working-memory savings. Native linear memory
still occupies two fixed pages. Ordinary translations are unchanged. HQ4's
requested alias `hq4-chego-auto` resolves to actual `hq4-chego-tiny`.

## Validation

All1649 Node tests passed, zero skips,79.98s. New checks compare all123 official
instruction forms with four C/Z combinations at internal and unequal external
CLKI edges and adjacent1ps deadlines. They also cover branch dataflow,
read-before-write, f64 dependencies, nested-barrier rejection, latched RET bytes
after debugger SRAM edits, RESET at each CALL half phase, cache isolation,
SPM under a held source and invalid options with precompiled input.

The first full run found the new JS dependency missing from the isolated loader
test's copied file inventory. That inventory was corrected, the focused loader
checks passed and the full run above passed afterward. Architecture layers and
the module dependency remain explicit.

The final13-workload matrix retains26 parity runs and168 exact checkpoints:
three firmware images in both modes, two direct kernels,20MHz CLKI /1,/256,
internal20MHz and internal/external active ADC. Per block, PCM bytes, complete
architectural/diagnostic state and pins match the full-context path. This is
software-model equivalence, not silicon measurement or an audio underrun gate.

## Timing decision

An initial eight-trial/four-warmup screen used fresh precompiled CPU Modules.
Its median ratios were1.034x/1.061x for rhythmic/HQ4, but identity controls
were unstable (up to1.069/1.082 median). It does not establish a speedup.

A second screen uses the normal production translation cache and asserts
shared CPU Module identity within identical-binary pairs; all labels still get
fresh native instances/memories. Sixteen balanced four-label trials and eight
warmups per label run with `--expose-gc`; GC is invoked after construction,
outside execution timing. Native runtime and generated CPU hashes match the
first screen. The annotation/admission fixes do not change those CPU bytes.

| Cached physical case | Old identity median | New identity median | Cross median | Faster trials |
| --- | ---: | ---: | ---: | ---: |
| rhythmic | 0.988 | 0.976 | 1.018x | 10/16 |
| HQ4 | 1.054 | 1.028 | 1.033x | 9/16 |

Ratios above one favor live locals. Individual identity observations range
0.762–2.032 and0.698–1.129 for rhythmic; HQ4 ranges0.713–1.230 and0.777–1.143.
This variation exceeds the proposed gains. Do not infer a physical-mode speed
improvement or enable the option by default from these measurements. The full
13-case *performance* gate remains open; its parity matrix is complete.

Together the two timing screens retain192 timed runs,96 discarded warmups and
3456 exact checkpoints. Construction, compilation, snapshots, hashing and GC
remain outside execution timers. One-off compile/generation observations do not
prove cold-start speed or browser performance. No Binaryen pass is combined
with this experiment.

## Reproduce

```sh
node --test web-player/tests/avr-phase-locals.test.mjs
node web-player/scripts/benchmark-generated-wasm.mjs --transform phase-locals --baseline-ref c8cf6bd --validate-only --out build/benchmarks/phase-locals-validation.json
node --expose-gc web-player/scripts/benchmark-generated-wasm.mjs --transform phase-locals --baseline-ref c8cf6bd --trials 16 --warmups 8 --case rhythmic-physical --case hq4-chego-auto-physical --out build/benchmarks/phase-locals-cached-screen.json
node web-player/reports/phase-locals-20261025/verify-evidence.mjs
```

[Initial screen](phase-locals-20261025/initial-screen.json),
[cached screen](phase-locals-20261025/cached-screen.json),
[validation](phase-locals-20261025/validation.json) and separate exact source
snapshots preserve each measured version, including the initial annotation
guard and loader-admission differences. The verifier recomputes ratios, checks
source hashes, baseline identities, unchanged timed CPU hashes, parity digests,
workload coverage and counts. Commits `b21392e` and `3d00f37` retain the final
implementation and harness. The device plan remains21/30, with nine items open.

Next compiler work is cross-block SREG liveness with all externally observable
exits preserved; default activation of phase-local liveness still needs a
stable full performance gate. Hardware-phase acquisition remains independent.

Primary semantics: [WASM local/structured-control execution](https://webassembly.github.io/spec/core/exec/instructions.html),
[AVR manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny13A datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
