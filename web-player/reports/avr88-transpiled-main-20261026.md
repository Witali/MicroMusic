# AVR → WASM player integration, 2026-10-26

Integrated `main` at `9a1b1bb6` with the AVR translation branch at `2a04aa0b`.
The two conflicts were generated `attiny13a.wasm` / `device-build.json`; the
physical runtime was rebuilt from the combined sources, retaining both main's
CPC/CPSE support and the branch's peripheral/dispatch optimizations. The merged
runtime is 118,969 bytes, import-free, with two fixed memory pages and 109
function exports. The adjacent build manifest pins its sources and hash.

ATtiny88 CPU translation now uses a separate device profile generated from
[Microchip ATtiny_DFP 3.4.278](https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack).
Original C/assembler/ATDF files and licensing are retained unchanged. Flash and
SRAM bounds, SREG, SPL/SPH and the legacy control registers come from those files.
Wide pointer and stack lowering uses existing WASM integer operations; ATtiny13A
keeps its low-byte pointer semantics. See the manufacturer's
[ATtiny48/88 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf)
and the [WASM binary instruction specification](https://webassembly.github.io/spec/core/binary/instructions.html).

The shared music runtime supplies ATtiny88's existing Timer1/audio model at the
entry's actual CPU clock. This does not add a full physical ATtiny88 peripheral
model or an ATtiny88 offline package format. The full ATtiny13A device runtime
remains available through its API and imported packages.

The current music (both chips/boards) and speech pages expose exactly three
choices: JS, WASM, AVR → WASM. No chip-name option follows that selector.
Switching chips/boards retains AVR → WASM. Imported ATtiny13A packages select
the same visible option and run their supplied physical runtime. WASM remains
the default engine.

## Validation

```
node web-player/scripts/generate-attiny88-registers.mjs --check
node --test web-player/tests/*.test.mjs tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
```

All **1,866 tests passed**, zero skipped, in 89.21 seconds on this host.
New coverage compares all 27 ATtiny88 entries (UM88 8 MHz, MH-ET LIVE 16 MHz,
legacy catalog) against the JS reference at audio block sizes 1, 127, 1024 and
4096: exact PCM, raw PWM, data memory, timer/cycle/IRQ state and IRQ frames.
Additional cases cover X/Y/Z page carry/borrow in instruction and optimized
block execution, SPL/SPH boundary crossings, calls above the ATtiny13A Flash
range, immutable manufacturer definitions, cache/clock isolation and UI choices.
The package renderer's AVR → WASM alias matches the existing device renderer;
the isolated JavaScript-only package loader also passed with no default WASM.

Built-in browser checks after the test run: actual Worker/AudioWorklet playback
on ATtiny88 8 MHz and 16 MHz, chip switching to ATtiny13A with the translated
engine retained, and speech playback through completion. Visible AVR cycle/IRQ
counters advanced with zero lost IRQ in the inspected states. The selector had
only the three requested choices. These are functional checks, not balanced
performance measurements or a sustained no-underrun guarantee.
