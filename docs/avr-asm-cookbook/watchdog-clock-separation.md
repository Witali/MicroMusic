# ATtiny13A: separate watchdog flags, counter resets and CPU service

Microchip [DS40002307A sections8.4/8.5.2](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=48)
distinguish WDTIF clearing from execution of the interrupt vector. In combined
mode an unserviced first interrupt still leads to reset at the next timeout.
WDR restarts the counter; writing WDTIF clears the flag. Neither substitutes
for vector service.

For the full ATtiny13A C/WASM board, test these as three independent operations:

- The watchdog oscillator supplies timeout pulses even with CLKI held.
- CPU clock delivery permits wake cycles and IRQ entry, then WDTIF/WDTIE
  acknowledgment; a pending flag alone cannot run a handler.
- Reset releases port drivers at the watchdog timestamp, while subsequent
  source CK controls reset-pulse completion and CPU restart.

Use actual source-only AVR firmware and manufacturer-derived register masks.
Observe an ISR-driven pin as well as flags, stack, reset count and CPU state.
Test W1C without an ISR, WDR after that flag, and held high/low clocks. A module
test of the watchdog counter alone cannot establish the board/CPU ordering.

The [20-case audit](../../web-player/reports/watchdog-modes-20261101.md) uses
AVR core instructions on ATtiny13A, with native Clang24 freestanding wasm32 C11
and no AVR assembler or additional ABI/ISA extension. Its explicit fixture has
1 MHz CPU and 128 kHz watchdog: first timeout 16 ms, next timeout 32 ms. WDR at
16.009 ms resets after oscillator pulse 2049, moving reset to pulse 4097
(32.0078125 ms).
Those are rational fixture outcomes, not measured chip accuracy. Both execution
policies preserve exact reset-pin snapshots and require actual CLKI to restart.

This is a correctness/verification technique, with no speed, code-size or
working-memory optimization claim and no change to production WASM.
