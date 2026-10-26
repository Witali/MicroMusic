# Preserve live SREG across flag-neutral instructions

NOP, LDI, MOV, MOVW and SWAP no longer load and restore SREG in their generated
instruction bodies. A basic block containing only those operations omits the
same pair, retaining its resumable pending-IRQ guard's SREG.I read. Mixed
blocks and cyclic regions retain their existing handling. No native runtime,
device definition, clock barrier, retirement or IRQ service was changed.

This repairs a public debugger-observation error: pause 1 ps into a one-cycle
instruction, edit SREG, then continue to 1 us in the declared 1 MHz fixture. The old
body restored its initial flags, overwriting the edit. An edited I bit also
failed to enable the Timer0 IRQ due at that instruction's completion. The new
body preserves the current architectural SREG instead of committing an unused
snapshot. RESET can still cancel the instruction before its register effects.
This correctness property applies even with flag liveness optimization disabled.

The identical 26-case regression passes 7/fails 19 on baseline 23c4b7b2 and passes
all 26 after the repair. It covers both phase-local policies, five tied Timer0
IRQs, five RESET cancellations, 2560 direct instruction/input-SREG cases
against native C for ATtiny13A/ATtiny88, and emitted-body SREG references in
four modes. The physical observation fixture uses the existing digital model;
no chip measurements were made.

All 2026 default/shared-tool tests pass, with no failures, cancellations or skips
(134487.9333 ms for the complete run). The generated compiler cache identity was
regenerated and its source-graph check passes.

The static comparison uses nine firmware catalog entries with default compiler
options and these policy additions:

| Policy | Modules | Saved bytes per module | Reduction |
| --- | ---: | ---: | ---: |
| Legacy music core | 9 | 1502–2484 | 0.896–1.516% |
| Full compatible device | 9 | 1561–2528 | 0.889–1.486% |
| Resumable device | 9 | 1494–2448 | 0.393–0.638% |
| Resumable, bounded regions and live phase locals | 9 | 5218–8671 | 1.825–2.942% |

Every old/new module validates. The last policy also sheds unused flag spills
around suspension points; it remains explicitly selected. These are whole
generated-module sizes, not an execution-speed measurement. Native WASM stays
119010 bytes with SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
No real-time audio speedup or newly validated hardware profile is claimed.

An additional old/new execution comparison captures 4096 frames at 48 kHz for
`rhythmic` and `lumiere-stereo`, both with conservative verification options
and explicitly enabled bounded regions/live phase locals. All four cases have
active interrupts. Every 256 frames, PCM, retained physical pin records including
timestamps, register/data memory, EEPROM/Flash, native diagnostics, PC/cycles,
retirement and physical time match exactly. All six pins are explicitly
observed with `retainDuringAudio:true`; default audio capture alone does not
retain that trace. This establishes equal output for these spans, not wall-time
throughput or a broader real-time acceptance result.

[The machine-readable evidence](neutral-sreg-20261026.json) pins the baseline,
compiler, harness, fixture and catalog hashes, plus each artifact's size/hash.
Reproduce from the repository root; baseline files and TAP logs stay under
ignored `build/`, without replacing the checkout:

```text
node web-player/scripts/verify-neutral-sreg.mjs --output build/neutral-sreg-evidence.json
node --test web-player/tests/*.test.mjs tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

The broad register-traffic/performance item remains open, as do the other six
open requirements: overall plan status stays 23/30. Native C/WASM remains
selectable. [Cookbook and constraints](../../docs/avr-asm-cookbook/neutral-sreg.md).
Official basis: [Microchip AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
sections 5.69/5.75/5.76/5.81/5.121, all with unaffected SREG bits.
