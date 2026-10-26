# Adaptive region budgets: measured HQ4 improvement

Commit `01ed0b38`: the optional boundedRegions path can admit a smaller register-only region
before a deadline. Previously it declined unless its entire worst-case budget
fit. Against the same native runtime, HQ4 physical measures 1.764x in the short
screen and 1.628x in longer confirmation, faster in all eight pairs in both.
The internal arithmetic kernel measures 1.614x/2.086x. Other gains are unproven;
the inactive CLKI control has a possible small loss. This remains opt-in.

## Change and correctness boundary

Baseline generator: `fc40b21a`. Only avr-transpiler.js and avr-wasm-regions.js
change among library inputs. The native image stays byte-identical: 118,946
bytes, SHA `1fe4bef5bdc458bb8ca2a65636221e4b5ed87a4d5003eca6b60532c4baf45b9f`.
Native flags, 109 function exports, two-page linear memory and 8192-byte stack
limit remain unchanged, with no host imports. Generated CPU imports still call
native WASM; no per-instruction JavaScript callback is added. CPU code is emitted
directly as MVP WASM; the native Clang 24/Binaryen 133 image is not rebuilt here.

Use the least of the native event bound, converted caller deadline and the
2^52 exact-half-cycle ceiling. If the original min(remainingInstructions,32)
worst-case span fails, derive a smaller positive integer budget strictly below
that bound; decline below two instructions. The conversion range is proved
finite and at most 96 cycles. Preserve pending IRQ/delay/continuation guards,
uint64 retirement headroom and every external-entry fallback.

All original region membership, instruction costs and full observable SREG
effects stay unchanged. Memory/I/O/stack/control operations remain outside
regions. Cached GPRs and SREG publish only after the successful native clock
barrier. Native peripherals and physical timestamps retain their existing
event processing. CLKI still supplies a zero region budget and never admits
positive region execution; physical source edges are not omitted.

Each region function adds one f64 local after its existing i32/GPR locals.
Linear memory and ABI do not change; host JIT register/stack allocation is not
claimed unchanged. The old and new region plans/manifests match. CPU size/hashes
are retained per firmware: music modules grow by 56/56/140 bytes, the two kernels
by 28 bytes. With boundedRegions=false the generated CPU bytes
match the old generator in all five control cases. Older packaged CPU code
remains valid. The proof and constraints are in the
[region budget audit](../native/region-budget-audit.md).

## Paired Node measurements

Node 22.22.3 / V8 12.4, Windows, Ryzen 5 5600X. Each case uses identical target,
ABI, options, native Module and host adapter for all four labels. Both pairs
select boundedRegions=true; only generator versions differ. OldA/oldB and
newA/newB are identical-byte controls. Every instance and CPU Module is fresh.
Construction/compilation, input setup, snapshots and hashing are outside timers.
Four full-workload warmups per label precede eight Williams-design trials.
Runs are serial; no tests, builds, profiles or live browser audio run alongside
the timings. Host load, CPU frequency, GC and JIT tiering remain uncontrolled.

| Physical workload | 12,000/1,200-frame screen | 48,000/4,800-frame confirmation | Long pairs faster | Long old/new identity medians |
| --- | ---: | ---: | ---: | ---: |
| Rhythmic | 1.029x | 0.999x | 4/8 | 0.938x / 0.926x |
| Lumière | 0.977x | 1.069x | 5/8 | 1.078x / 0.993x |
| HQ4 (`hq4-chego-tiny`) | 1.764x | 1.628x | 8/8 | 1.006x / 1.017x |
| Internal 20 MHz /1 kernel | 1.614x | 2.086x | 8/8 | 0.929x / 0.977x |
| CLKI 20 MHz /1 kernel | 0.985x | 0.953x | 3/8 | 1.038x / 0.952x |

Each matrix contains 160 timed runs / 80 warmups. Combined with the five-case
old/new parity matrix: 320 timings / 160 warmups, 9,248 snapshots and 9,017
comparisons. Every checkpoint preserves exact PCM, complete public/diagnostic
state, data/Flash/EEPROM/IRQ and retained pin history. Audio may drain history;
these hashes do not independently capture every physical edge or silicon signal.

HQ4's long pair range is 1.412–1.887x, and the internal kernel's 1.718–2.421x.
Both gains are larger than their identity control movement and repeat in both
intervals. Do not generalize to other firmware/hosts. Rhythmic/Lumière results
do not establish gains. CLKI does not activate positive regions, but its code
image/JIT placement changes; the long 0.953x cannot exclude a small loss.
boundedRegions=false remains available and byte-identical for that workload.
No exact exclusive CPU/peripheral time or cause of all elapsed changes is inferred.

## Regression and browser validation

All 1,729 default/shared-tool checks pass, zero skips (182.51s), including 24
region cases. Seven new cases cover actual smaller admissions at exact and
adjacent 1ps deadlines, clock-before-commit through queued input/RESET,
three-cycle skips and early exits, exhausted/past float bounds, reduced-budget
uint64 retirement headroom, ADC conversions and watchdog ISR during audio.
Existing whole-form, flags, phase-local, package, SPM, CLKI and IRQ tests remain.

The browser checks three actual packages against boundedRegions=false with
active IRQs: exact filtered/raw PCM, full state/memory/IRQ and pins at twelve
checkpoints. Its live Worker/AudioWorklet test compares boundedRegions=false
against the new true path; it does not compare the two Node generator versions.
The retained browser JSON records the actual clock, visibility, queue underruns
and IRQ activity. Browser real-time acceptance is reported separately from the
Node speedup and must not be inferred from it.

Chrome 156 in the built-in browser passed all twelve parity checkpoints. Six
sequential 10-second live-audio cases stayed visible, their AudioContexts ran
for 9.96–9.99s, all delivered firmware IRQs and none reported a device fault.
They nevertheless all failed real-time acceptance: underrun episode counts
for false/true were Rhythmic 12/18, Lumière 16/16 and HQ4 17/4. HQ4's true path
consumed 435,712 frames, still short of the live audio clock. These are single
sequential browser observations, not balanced old/new-generator speed ratios.
They do not establish a supported real-time profile. The default remains wasm.
See the [browser JSON](adaptive-region-budget-20261025/browser.json) and
[visible result](adaptive-region-budget-20261025/browser.png).

## Evidence and replay

[Evidence](adaptive-region-budget-20261025/) retains the two candidate generator
sources, the test source, raw matrices and full TAP compressed as gzip, browser
data, driver snapshots and an isolated replay. The timed driver and replay
driver differ only by --full-tree for historical library enumeration, so replay
works from a nested ignored directory. This is a setup-only correction, outside
capture timers; both original timed-driver hashes remain verifiable.

The verifier checks all pinned source/native identities, per-run observations,
ordinary-path byte checks made by the driver, and recomputed paired statistics.
Optional reconstruction restores pinned inputs and the two candidate generators
in a fresh ignored tree, runs the region contract tests and regenerates both
CPU versions for all five parity cases. Production files are not overwritten.
The recorded isolated run passes all 24 region tests and reproduces the exact
CPU hashes and observations for all five pairs.

```sh
node web-player/reports/adaptive-region-budget-20261025/replay.mjs
node web-player/reports/adaptive-region-budget-20261025/replay.mjs --rebuild
node web-player/scripts/benchmark-region-budgets.mjs --baseline-ref fc40b21a --validate-only
node --test web-player/tests/*.test.mjs tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
```

The default engine remains wasm; the hardware checklist remains 21/30 with nine
open. This improves one optional execution policy, not silicon fidelity or the
unresolved native idle-ADC performance penalty. Physical captures, Timer0 TOP=0,
debugWIRE, persistent/region cache and full default-engine acceptance stay open.

Primary references: [Microchip AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[WASM binary numeric instructions](https://webassembly.github.io/spec/core/binary/instructions.html#numeric-instructions)
and [numeric semantics](https://webassembly.github.io/spec/core/exec/numerics.html).
