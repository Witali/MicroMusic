# ADIW/SBIW unsigned word loads and stores

The AVR→WASM emitter now loads and stores uncached ADIW/SBIW register pairs
using `i32.load16_u`/`i32.store16`. This replaces two byte loads, shift/OR and
two byte stores. The existing `i32.add/sub`, 16-bit wrap, flag equations and
retirement remain. Cached regions retain byte locals. Microchip
[DS40002198A sections5.3/5.98](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
define the supported pairs, immediates, two AVRe cycles and S/V/N/Z/C changes;
I/T/H stay unchanged. The [cookbook](../../docs/avr-asm-cookbook/movw-word-lowering.md#adiwsbiw-register-pair-arithmetic)
records the existing ABI, WASM opcodes and phase constraints. The correspondence
table is updated for ADIW/SBIW and the already retained MOVW word copy.

All **96 focused checks and 2862/2862 default tests pass**. The new 29 cases
cover all 512 encodings in seven
engine/policy modes with boundary values and every retained I/T/H pattern,
actual word opcodes, odd ABI alignment, cached register dependencies, uncached
blocks with dead flags, partial host edits, IRQ/RESET and held/unequal CLKI.
Existing independent tests exhaust all 65536 input words and all 64 immediates.
The MOVW and new arithmetic checks share a small test-only WASM body reader.

The [historical verifier](../scripts/verify-word-lowering.mjs) pins baseline
`4a603b2f` and current source graphs, redirects only unchanged compiler imports,
and runs original/new CPU modules against the same native artifact:

- All 48 catalog/policy artifacts have unchanged semantic manifests.
- Twenty shrink by 23–184 bytes each; the other 28 are byte-identical. The sum
  across these artifacts is 2346 bytes, not a single module's saving.
- All unaffected functions and register-cached region bodies are byte-identical.
- Eight paired music cases cover Rhythmic, Lumière stereo, Alicia and HQ4 Tiny
  under compatible/physical configurations, with 128 full-state/PCM/pin
  checkpoints, 15982 active IRQs and 34422 retained pin events.
- Both distributed native WASM files, memory, ABI and native clock/IRQ calls
  are unchanged. The compiler/cache identity is refreshed for the new code.

The [evidence record](word-lowering-20261101.json) retains each artifact's sizes
and hashes, parity counts, source graphs and TAP hashes. No host execution-speed,
real-time audio, silicon or complete stage5 benefit is claimed. The source
change reuses existing word-access helpers and adds no option, runtime import
or firmware requirement. There are no new downloads.

The earlier SRAM census was inspected before choosing this change. HQ4's
50,000-instruction prefix has only 58 executions of its apparent adjacent
LDS/STS pair; that does not justify a two-word-span extension on its own.
This checkpoint does not broaden SRAM batching or revive rejected incoming-SREG
elimination, constant folding or inter-block flag fusion.

Reproduce at this checkpoint:

```sh
node --test web-player/tests/avr-word-lowering.test.mjs web-player/tests/avr-movw-lowering.test.mjs web-player/tests/attiny13a-transpiled-isa.test.mjs web-player/tests/avr-neutral-sreg.test.mjs web-player/tests/avr-neutral-regions.test.mjs
node web-player/scripts/verify-word-lowering.mjs --output build/word-lowering-evidence.json
```

The hardware checklist remains **24/31 complete, seven open**.
