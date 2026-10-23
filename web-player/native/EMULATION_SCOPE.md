# Emulation scope

## Firmware loading and execution

The virtual ATtiny13A starts from a supplied firmware image. The binary is
translated into WASM and executed with the configured CPU, peripherals and
initial memory state. Package loading restores those inputs.

## No virtual-chip programming interface

The project does not program a virtual chip through an external programmer.
ISP/SPI programming, high-voltage serial programming (HVSP), programming-mode
entry and programmer command transports are outside the current scope. They
are not required acceptance criteria for this transpilation plan.

Do not implement these interfaces or add a programming backend unless the user
explicitly requests that work separately. Firmware loading initializes the
emulated device directly from the supplied image.

CPU-visible EEPROM and SPM instruction behavior belongs to firmware execution;
it does not provide an external programming interface.

This boundary records the user's scope decision on 2026-10-23. See
[`ATTINY13A_PLAN.md`](ATTINY13A_PLAN.md) for execution work and
[`ARCHITECTURE.md`](ARCHITECTURE.md) for source/generated-artifact separation.
