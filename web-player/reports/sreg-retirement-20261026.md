# Retire only the documented SREG bits

Generated individual instructions now commit only their documented SREG write
mask. This extends the [five-operation repair](neutral-sreg-20261026.md) to all
123 ATtiny13A instruction-summary forms, including aliases and addressing modes.
Read-only flag users such as BRxx and BLD retain their latched inputs without
restoring an old complete SREG. Transfers, stack and system operations without
flag effects omit the flag snapshot and commit. Explicit OUT/STS/indirect ST
aliases of SREG continue to write the complete value through the device bus.

For a resumable instruction with mask M, the final write is:

```text
SREG = (current_SREG & ~M) | (computed_flags & M)
```

For example, ADD changes H/S/V/N/Z/C but preserves the current I/T. Previously
it could overwrite debugger edits to I/T made during a clock pause. INC must
also preserve H/C; CLI, SEI and RETI change only I. BSET/BCLR select exactly one
decoded bit, even though their generic manual table lists the union of possible
write bits. No-write instructions now perform no retirement SREG store.
Bus writes and their protected timing are independent of this ALU flag mask.

This does not change flag equations or the existing operand-read phases.
ADC/ROR still consume latched carry, SBC/SBCI/CPC consume carry and prior Z,
BLD consumes T, and branches use their captured condition. ADC computes its
own Z; subtraction-with-carry uses chained Z. Existing exhaustive operand/
integer-oracle and independent-execution tests remain in the full test run.
The public edit tests establish the emulator's observation contract; they do
not establish undocumented silicon latch phases.

## Official documentation audit

`audit-avr-sreg.py` extracts the eight-bit flag row from the detailed instruction
descriptions in Microchip DS40002198A. It first requires the exact pinned PDF
SHA-256 `d8e75ad7cc92de2b86c718495ed9392096e0192a08269a4dba8da16075be1e00`.
Every one of the 123 catalog masks matches. Missing or mismatched rows fail the
audit; known PDF headers/footers are removed to handle the CPSE page break.
This audit checks write masks, not a machine proof of the Boolean equations.

| Instruction family | Written SREG bits |
| --- | --- |
| ADD/ADC, SUB/SUBI, SBC/SBCI, CP/CPI/CPC, NEG; LSL/ROL aliases | H S V N Z C |
| ADIW/SBIW, COM, LSR/ASR/ROR | S V N Z C |
| INC/DEC, AND/ANDI, OR/ORI, EOR; TST/CLR/CBR aliases | S V N Z |
| BST | T |
| CLI/SEI/RETI | I |
| BSET/BCLR and their flag aliases | Selected bit |
| Other forms, including BLD and BRxx | None, except explicit data-bus SREG aliases |

The official PDF stays outside retained source files; the evidence records its
manufacturer URL, digest and derived masks with section/page references. Device
addresses still come from the original pinned Microchip DFP definitions.

## Verification

The same 296 tests pass 53/fail 243 on baseline 47fe829b and pass all 296 after
the repair. They cover both phase-local policies, both complementary initial
flag patterns, pauses 1 ps after successive half-cycle boundaries, all catalog
forms, explicit SREG read/write aliases, 38 tied Timer0 IRQ cases and six RESET
cancellations. Generic BSET/BCLR fixtures select bit zero; their separate aliases
cover other selected bits. Tests compare unaffected memory, PC, cycles, physical
time and retirement as well as SREG. All 2322 default/shared-tool tests pass,
without failures, cancellations, skips or TODOs (122654.901 ms for the full run).

Old/new physical captures also match for `rhythmic` and `lumiere-stereo`, with
4096 frames at 48 kHz in both conservative verification and explicitly enabled
bounded-region/live-local policies. All six pins are retained during capture.
PCM, timestamped pin records, CPU/data/EEPROM/Flash state, native diagnostics,
retirement and physical time match every 256 frames. Each case has 798 IRQs;
pin counts are 1597/1877 respectively. No host edits occur in those comparisons.

The extra partial-write merge has a small static cost in conservative modules;
removing unnecessary flag spills can outweigh it under live-local optimization:

| Firmware/policy | WASM bytes before | After |
| --- | ---: | ---: |
| rhythmic / verification | 423369 | 424025 |
| rhythmic / bounded phase locals | 294424 | 290760 |
| lumiere-stereo / verification | 427890 | 428609 |
| lumiere-stereo / bounded phase locals | 297425 | 293878 |

No execution-speed or broader real-time acceptance claim follows. Native WASM
remains 119010 bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
No peripheral timing, DWEN/debugWIRE support or hardware-measurement item closes.
The overall plan remains 23/30, seven open.

[Evidence and source hashes](sreg-retirement-20261026.json). Reproduce with Python
and `pypdf`, then Node; supply the official PDF path locally:

```text
python web-player/scripts/audit-avr-sreg.py --manual path/to/AVR-Instruction-Set-Manual-DS40002198A.pdf
node --test web-player/tests/*.test.mjs tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs > build/sreg-retirement-full.tap
node web-player/scripts/verify-sreg-retirement.mjs --output build/sreg-retirement-evidence.json
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

The verifier freezes the baseline under ignored `build/` without changing the
checkout. `MICROMUSIC_DEVICE_MODULE` also selects an independent loader for
direct regression replay. No firmware source MIDI or hardware programmer is used.
Official sources: [Microchip instruction manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny13A datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[WASM memory instructions](https://webassembly.github.io/spec/core/syntax/instructions.html#memory-instructions).
