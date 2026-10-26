# MH-ET LIVE Tiny88 common-core acquisition fixture

The user has this 16 MHz USB/Micronucleus board. This fixture tests twelve
common AVR instruction cases: results, SREG, branch/skip behavior and total
cycles calibrated against Timer1 /1. It cannot establish ATtiny13A-specific
ADC, Timer0, RESET or internal bus-phase behavior. Interrupts are disabled;
there is no real-time audio/underrun claim.

From the repository root:

```text
node web-player/scripts/build-avr-core-probe.mjs
node web-player/scripts/check-avr-core-probe.mjs --out build/probes/avr88-core/software-check.json
node --test web-player/tests/avr-core-probe.test.mjs
```

The builder locates the prepared AVR-GCC 7.3.0 toolchain in this checkout or
its parents; alternatively pass `--avr-bin <directory>`. Outputs stay in
ignored `build/probes/avr88-core/`. `--nonce <unique-run-name>` changes the
four-byte run identity. Retain the exact descriptor and Flash hash with any
capture. The original Microchip `iotn88.h` from ATtiny_DFP 3.4.278 is hash
checked and selected first; project adaptations do not edit vendor files.

The assembled image is 1284 bytes (conservative application limit 6012).
Software checks execute it in JS, C/WASM and AVR → WASM, both from reset and
with inherited watchdog/stack state. All six runs reach `probe_measured`
after 7488 instructions / 9289 cycles, with all twelve cases passing and
five timer ticks of calibrated read overhead. Whole CPU/data snapshots agree
between engines. This boundary is **before EEPROM programming and LED output**,
which the Tiny88 music runtime does not model. These are software outcomes,
not measurements of the user's board.

Actual execution replaces the board's current application and writes all
64 EEPROM bytes. This preparation has not uploaded anything. Before a future
authorized upload, preserve the existing application and EEPROM using a
compatible readback tool. Keep fuses and the bootloader unchanged. The board
profile is documented in [the board guide](../../../../ATtiny88/Music/MH_ET_LIVE_RU.md).
Its nominal 16 MHz exceeds the manufacturer's ordinary 12 MHz rating, so a
failure cannot automatically be attributed to emulator behavior.

After saving EEPROM, the D0/PD0 status LED repeats one pulse for all-pass or
three for failure. USB D1/PD1 and D2/PD2 are left alone. A visible all-pass
indication provides a coarse result; detailed evidence needs a raw 64-byte
EEPROM dump from a loader/programmer supporting readback. Stock loader
capabilities must be checked before assuming that readback is available.

```text
node web-player/scripts/decode-avr-core-probe.mjs --descriptor build/probes/avr88-core/descriptor.json --eeprom <raw-dump.bin>
```

The `AVR1` record contains version/count, pass count, completion marker, run ID,
calibration overhead, CRC16-CCITT-FALSE and twelve four-byte results
`value/SREG/timer-low/timer-high`. CRC covers bytes 0–13 and 16–63, with byte 7
normalized to zero. EEPROM byte 7 is invalidated first and committed to `A5`
last, after the other 63 bytes. The decoder rejects incomplete/corrupt records,
wrong run IDs and inconsistent pass counts; decoding alone does not certify
acquisition provenance.

Primary references:

- [ATtiny48/88 datasheet 8008H](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf): Timer1, EEPROM, instruction cycle totals and speed grade.
- [AVR ISA DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf): instruction results and SREG.
- [Pinned original manufacturer definitions](../../../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
- [Measurement wrapper and ABI constraints](../../../../docs/avr-asm-cookbook/timer-calibrated-core-probe.md).
