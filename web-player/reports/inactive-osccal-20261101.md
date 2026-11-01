# OSCCAL writes with an inactive calibrated RC source

Physical external and 128 kHz profiles previously rejected an OSCCAL write
when the RC frequency table lacked the new CAL point, although the selected
CPU source was unaffected. Such writes now update the seven-bit register
without requiring or inventing an unused RC frequency. Active calibrated
sources still require known CAL frequencies; the legacy fixed-clock fixture
retains its existing admission rules. The external CLKI behavior is preserved.
The [CAL contract](../native/peripherals/device-osccal.md) links the official
clock diagram and register semantics.

Six native regressions reproduce the incorrect rejection before the fix.
All **51 focused checks** now pass. They cover all 256 write bytes for both
inactive source choices, reserved-bit masking, exact fractional clock phase,
Timer0 progression, reset restoration, and both active RC-source controls.
Generated LDI/OUT/IN firmware and its package reload retain exact state and
three-cycle execution for both inactive source selections.

EEPROM and Flash programming still require a separate timing profile; neither
operation starts without it. Explicit fixed-ns tests preserve completion
deadlines through additional unknown-CAL writes, including the instant 1 ps
before completion. Those are declared timing fixtures, not measured programming
safety at an uncharacterized RC frequency. Historical packages retain their
embedded runtime behavior; the correction applies when using the new runtime.

The final default suite passes **2669/2669**, with no failures or skips.
The [JSON evidence](inactive-osccal-20261101.json) binds that full-suite
result, focused/before TAP hashes, native/host/test source graphs and isolated
rebuild. Both default and isolated builds produce the same native artifact.
Compiler flags, 17 C sources, 117 function exports, no imports, two fixed memory
pages and the resumable ABI remain unchanged. The legacy AVR WASM artifact and
generated AVR instruction emitter are unchanged. The loader URL and compiler
cache identity are refreshed for the new runtime.

No speed, measured calibration, electrical safety or silicon phase claim is
made. The plan remains **24/31 complete, seven open**.

From the repository root, with the already registered SDK:

```text
node web-player/scripts/build-device-wasm.mjs --out-dir build/inactive-osccal-rebuild-20261101
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/device-osccal-runtime.test.mjs web-player/tests/attiny13a-physical-clock.test.mjs web-player/tests/attiny13a-clki-runtime.test.mjs
```

Run the default full suite with `npm test` from `web-player`. Raw TAPs and build
proof inputs remain under ignored `build/`. No software was downloaded or
installed; the pinned official datasheet, definitions and toolchain are reused.
