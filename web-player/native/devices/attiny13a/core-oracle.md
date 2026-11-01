# ATtiny13A instruction controls for Microchip Studio

This is a prepared, assembled control fixture. **No official simulator session
has executed.** The [host prerequisites](reference-host-setup.md) still require
installation approval. The plan remains **24/31 complete, seven open**.

The original assembly scaffold and typed C mailbox live beside this document;
the builder, decoder and model-only verifier live under `web-player/scripts/`.
Generated ELF, binary, assembly include, `debughooks.py` and observations stay
under ignored `build/probes/`. Production device sources are selected explicitly
by `build-device-wasm.mjs`; this firmware is not linked into the player.

## Build and software preparation checks

From the repository root, using the already registered AVR GCC 7.3.0 toolchain:

```powershell
node web-player/scripts/build-attiny13a-oracle.mjs
node web-player/scripts/verify-attiny13a-oracle.mjs
node --test web-player/tests/attiny13a-oracle-record.test.mjs
python web-player/tests/attiny13a-oracle-hooks.test.py
```

Use `--avr-bin` if the registered compiler is elsewhere. The builder checks the
original ATtiny_DFP **3.4.278** header against its retained provenance; register
addresses are not copied into the fixture. No additional download is needed.

The 2026-10-30 build occupies **572 bytes Flash and 60 bytes SRAM**, leaving four
stack bytes. It contains DWARF2 types for `oracle_record`, twelve shared
[instruction stimuli](../../../scripts/lib/avr-core-probe-cases.mjs), an empty
timing control and a build identifier. Main forms are ADD, ADC, SUB, SBC, CPC,
LSR, ASR, ROR, ADIW, BRNE, CPSE and RCALL. A stimulus may include supporting
instructions; twelve prepared forms are not exhaustive input/flag coverage.
The descriptor retains preparation status for all 123 catalog rows, with every
official observation still false.

This is an assembly test scaffold, not a replacement arithmetic backend. It
keeps interrupts masked, disables the watchdog, ADC and comparator, and runs
Timer0 in normal mode at clkIO/1. WDTON must be unprogrammed. Only a two-byte
RCALL return address uses the reserved stack. Do not add interrupt/peripheral
experiments without revisiting the 64-byte SRAM budget.

Each case stores result, SREG and two TCNT0 readings. Subtracting the empty
control removes sampling overhead modulo 256. Sequences are short enough to
avoid ambiguous full wraps. The model verifier additionally checks the actual
CPU-cycle span of every sequence and that the stack is restored. These are
whole-instruction checks; they do not measure internal I/O read phases,
oscillator frequency or the 10 ns virtual-event requirement.

## Capture when the official host is available

Studio documents [ELF/DWARF2 object debugging](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-0A5C8A7E-FFD4-4442-A77B-C782712558BE.html)
and [project-local debug scripting](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-E6AEB04E-0C45-43E6-AB02-33AC01E3A513.html).
The latter uses IronPython 2.7 and loads `debughooks.py` when the debug session
starts. Our callbacks have only been exercised with Python 3 contract stubs;
the real host API binding remains unverified.

1. Use **Open Object File for Debugging** with the generated `oracle.elf`.
   Select **ATtiny13A / Simulator**, verify the actual device pack and record
   host, simulator and pack versions/hashes, clock and fuse settings. Start
   from reset rather than relying on a C `main` function. No external programmer
   or device-programming interface is involved.
2. Keep the generated `debughooks.py` beside the ELF. Set a breakpoint at
   `oracle_complete`, checking the disassembly against `stopByteAddress` in
   `descriptor.json`. Default hooks emit only an address-calibration notice;
   they do not read SRAM. The documented callback does not specify address
   units, so confirm bytes versus words at this specific stop in the real host.
3. Rebuild into a separate output directory with the observed unit:

   ```powershell
   node web-player/scripts/build-attiny13a-oracle.mjs --out-dir build/probes/attiny13a-studio-bound --breakpoint-address-unit bytes
   ```

   Use `words` instead if observed. Reload the new ELF and restart the debug
   session to load its matching hooks. A changed build identifier prevents
   collection of an old mailbox with a new helper.
4. Run from reset to the same stop. The helper reads only typed mailbox fields
   with `CalcNumericValue` and writes one JSON observation to the
   `MicroMusicOracle` output tab. It preserves breakpoints and watch expressions,
   performs no writes and prints generic read errors. Check Studio's output
   logging threshold if the tab is absent. Save only the JSON object following
   `MICROMUSIC_ORACLE ` as a local `observation.json`.
5. Compare the observation locally:

   ```powershell
   node web-player/scripts/check-attiny13a-oracle.mjs --descriptor build/probes/attiny13a-studio-bound/descriptor.json --capture build/probes/attiny13a-studio-bound/observation.json
   ```

The checker rejects an unconfirmed address unit, invalid bytes and stale build
IDs. It always retains `hostVerified:false`: a JSON record cannot establish
which debugger produced it. Preserve the verified host configuration and ELF
hash separately before treating a future capture as independent evidence.
The helpers are not a standalone Studio simulator CLI; `atprogram` provides no
simulation run/step command.

## Retained preparation evidence

The [2026-10-30 report](../../../reports/studio-oracle-preparation-20261030.json)
pins source and artifact hashes for unconfirmed and byte-bound builds. Both
passed twelve cases on our model; five decoder and six callback tests passed.
A clearly synthetic checker round trip passed and four invalid inputs were
rejected. The rebuilt production device WASM is byte-identical to the existing
artifact and its build inputs and compiler cache identity are unchanged.
There is no official-host, hardware, audio-performance or silicon-timing claim.
