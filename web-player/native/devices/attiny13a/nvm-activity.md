# ATtiny13A NVM activity contract

The board regularly services nonvolatile memory only while EECR.EEMPE is set,
SPMCSR contains a command, or EEPROM/Flash programming is busy. The predicate
reads the controller's existing state; there is no separately cached mask or
new device ABI. An idle controller is also absent from the two NVM deadline
queries. EEPROM-ready interrupt arbitration remains independent: EERIE can
assert a constant ready level while no timed operation is active.

Every NVM register read/write, reset, SPM and special LPM already calls
`nvm_advance` before its effects. These operations catch up both private time
fields at the actual bus/control timestamp before a new command can start.
During an idle interval, only those private timestamps can be stale; register
values, array contents, pending IRQ levels and shared register observations
remain current. Existing board deadline invalidations are retained.

Active CPU-cycle protection windows still expire at their exact edges. In
CLKI mode the second NVM advance after a delivered system phase is required
for these windows, even though asynchronous programming time was serviced
before that source edge. Busy programming remains active with a held source,
sleep, PRR, reset or a halted CPU. The supply guard and the ordering of NVM
completion, reset and voltage inputs are retained. No source edge is omitted.

The hardware basis is the official [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 5.3/5.5.3 and 16.6/16.9.1: EEPROM-ready IRQ is a level, EEMPE and
SPM commands have CPU-cycle windows, and programming completion uses its own
timing. The scheduler's exact digital tie policy is a model contract.

`tests/device-nvm-activity.test.mjs` compiles the real C board alongside an
unconditional-service reference in ignored test fixtures. Every operation
compares complete NVM control/payload state, shared registers, Flash/EEPROM,
clock/reset/IRQ observations and pin history; only the two deliberately lazy
private timestamps are normalized. Native entry counters prove that idle
advance/deadline calls disappear. Counters establish eliminated work, not a
production speedup. Tests include long-idle reactivation, ready IRQ without
timed work, exact command expiry, held CLKI, all EEPROM modes/stalls, Flash
halt/reset, sleep/PRR and one-picosecond supply/reset boundaries.
