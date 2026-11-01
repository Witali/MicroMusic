# Constant flags for self-comparison and subtraction

`CP Rd,Rd` and `SUB Rd,Rd` now emit constant live SREG bits instead of loading
both operands and calculating subtraction/flags. CP preserves the register;
SUB writes zero. I/T survive, Z is set and H/S/V/N/C are cleared. Only the
decoded equal-operand cases change. The existing CLR constant path supplies
the implementation with each instruction's original live flag mask. See the
[official semantics and examples](../../docs/avr-asm-cookbook/clr-constant-lowering.md#self-comparison-and-subtraction-2026-11-01).

The generated instruction still takes one AVR cycle. Register effects and
SREG commit remain after the original clock barrier. Public edits while paused,
RESET cancellation, tied IRQs, external CLKI holds and cached-region register
dependencies retain their existing contracts. The native runtime, hardware
scheduler, device definitions and both distributed WASM artifacts are unchanged.
The generated compiler/cache identity is refreshed for changed CPU bytecode.

## Evidence

The pre-edit CLR/SREG-observation set passes 20/20. All **34** new focused checks
pass. These cover every GPR/SREG pattern, independent exhaustive byte/SREG pairs
(65536 per instruction), nonaliased operand boundaries, dead and partial live
flags, full/legacy Tiny13/Tiny88 paths, cached regions, partial instruction
observations, RESET, tied Timer0 IRQs, and held/unequal external CLKI phases.
The default full suite passes **2651/2651**, without failures, cancellations or
skips. Counts and TAP hashes are retained in the
[JSON evidence](self-subtract-lowering-20261101.json).

Historical/current compilers use identical host wrappers and native runtime,
with cache reuse disabled. Across both firmware catalogs, **48** policy modules
validate, preserve manifests and leave every unaffected function body unchanged.
Four Alicia variants shrink; the other 44 modules remain byte-identical:

| Policy | Before, bytes | After, bytes | Saved |
| --- | ---: | ---: | ---: |
| Legacy | 171579 | 171448 | 131 |
| Full compatible | 178831 | 178701 | 130 |
| Resumable | 399271 | 399141 | 130 |
| Bounded regions + phase locals | 294748 | 294618 | 130 |

Six matched audio comparisons run Rhythmic, Lumière stereo and Alicia in
compatible/physical modes, 4096 frames each at 48 kHz. All 96 checkpoints match
PCM, full architectural/diagnostic state, Flash/EEPROM/SRAM/IRQ frames and
retained pin events, with 797–3198 serviced IRQs per case. The CPU module must
remain the selected historical/current instance throughout capture.

The unchanged native artifact is 124614 bytes, SHA-256
`b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`.
This is measured bytecode-size and verified operand-traffic reduction. Execution
speed, browser real-time audio/underruns and silicon behavior are unmeasured.
No new hardware mode or complete stage-5 claim follows. The plan remains
**24/31 complete, seven open**.

## Reproduction

```text
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/avr-self-subtract-lowering.test.mjs
node web-player/scripts/verify-clr-lowering.mjs --family self-subtract --baseline 81dc6d8f --output build/self-subtract-lowering-replay.json
```

The collector checks all other compiler-graph inputs and both native artifacts
against the baseline, retains source/catalog hashes and rejects changes outside
the selected alias family. Full-suite TAP remains local under
`build/self-subtract-full-20261101.tap`; `--full-tap` binds its counts/hash to a
report; `--focused-tap` binds the focused suite similarly. The pinned official
manuals/toolchain are reused; nothing was downloaded
or installed for this change.
