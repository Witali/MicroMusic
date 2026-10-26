# I/O publication ownership and observation audit

Audited against device.c at `9583026` and native SHA
`b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4`.
No publication optimization is retained. The scoped prototype passed correctness
checks but was [rejected after measurement](../reports/io-publication-scope-20261025.md).
The earlier [matched profiles](../reports/adc-regression-profile-20261025.md) leave
the idle-ADC internal-kernel regression unresolved.

## Current behavior

`mirror()` publishes 31 controller-owned I/O bytes to caller data-space memory.
It is called after clock service, reset/power handling, firmware bus writes,
IRQ acknowledgement, control/SPM/LPM operations and current-time input handling.
CPU GPRs, SREG/SPL and OSCCAL are not part of this publication set; preserve their
existing ownership. Reserved I/O reads have their own bus behavior.

The exact optimized mirror already loads board.data once into a local. Its31
byte stores are real; repeated pointer loads are not. Do not add a pointer cache
or claim a size/speed benefit for one without different generated code.

## Candidate register groups

Names/addresses are generated from the pinned official Microchip definitions.
The machine-readable [inventory](../reports/adc-regression-profile-20261025/register-inventory.json)
maps all 31 stores, with 16 software/bus/reset bytes and 15 dynamic bytes.
Grouping identifies possible publication ownership, not permission to skip it.

| Candidate group | Bytes | Mutations to cover |
| --- | --- | --- |
| ADC selection | ADCSRB, ADMUX | ADC register writes/reset. ADLAR also reformats visible ADCL/ADCH immediately; ACME affects comparator routing. |
| GPIO configuration/latches | DIDR0, PCMSK, DDRB, PORTB, MCUCR, GIMSK | GPIO writes/reset. A PINB bus write toggles PORTB, so tracking only writes to PORTB is insufficient. Alternate outputs do not replace its CPU latch. |
| EEPROM address/data | EEDR, EEARL | NVM writes/reset. EECR.EERE loads EEDR; reset during programming can preserve the pending address. Completion/windows remain dynamic. |
| Timer configuration/compare buffers | TCCR0A, TCCR0B, OCR0A, OCR0B, TIMSK0 | Timer writes/init. OCR readback is the programmed buffer; active compare values latch separately. Clock/sleep gates do not rewrite CS selection. |
| Power reduction | PRR | device_write/reset_state; retain clock-domain effects before considering publication. |

Keep ADCL/ADCH, ADCSRA, ACSR, PINB, GIFR, WDTCR, MCUSR, EECR, SPMCSR,
GTCCR, TCNT0, TIFR0, CLKPR and BODCR dynamic in the first candidate. This covers
conversion/result/flag changes, input synchronization, timed windows and strobes.
Do not merge this experiment with further controller clock gating.

Full mutation paths already publish after their effects. In particular,
power_sync HOLD/reset, reset_state and the reset_preapplied acknowledgement must
retain full publication; the CPU can clear its data view between reset stages.
device_write computes merged bytes using the data view, so that view must be
canonical before a later firmware read-modify-write can depend on it.

## Verified observation constraint

`device-io-publication.test.mjs` mutates the public data view for all 16 candidate
bytes, then clocks an otherwise ordinary configured device. Compatible and
physical internal clocks use clock(); CLKI uses a bounded periodic source with
runUntilPs(). All three restore the controller values, advance source time and
preserve an unrelated CPU-owned GPR. Direct typed-array edits are not firmware
bus operations, but this restoration is an existing observable API behavior.

An unconditional dynamic-only clock mirror would fail these tests. Source writes
alone cannot detect direct mutation of a typed-array view. Merely labeling the
registers software-owned, or only checking normal firmware, is insufficient.

## Evaluated scope contract

The rejected prototype used an explicit scope owned by one synchronous
native/generated execution call. Outside that scope retain full publication.
Within it, configuration can
be reused only after the shadow has been made canonical at the publication point
where the old implementation would do so. All actual mutations/reset stages
still publish their complete effects. Dynamic bytes retain original phase timing.

Do not normalize memory eagerly for zero-work calls: run(0), WAIT without a
publication event and a fault before any clock must preserve their existing
behavior. A zero-delta service that actually publishes must still do so. Trap,
reset, SPM refresh, buffer yield and partial instruction exits must release scope
ownership safely without committing later effects or advancing extra time.

Audit every public observation route before admitting this protocol: ordinary
step/run/capture, direct native clock/phase/wait exports, package/standalone CPU
entry and partial WAIT/fault/RESET observations. JavaScript cannot be assumed to
always enter through one wrapper. Historical runtimes need the unchanged full
path. Any optional begin/end capability needs validated signatures and balanced
cleanup; no per-edge JavaScript callback is allowed.

Validation must include these 3 raw-shadow tests plus zero-work and partial/fault
boundaries, complete memory/state/IRQ and retained pin/PCM parity, enabled ADC,
watchdog, internal/CLKI/divisor controls, SPM/packages and balanced native timing.
The expected benefit is fewer stores; no speed/size/memory claim follows until
actual code and measurements verify it. Browser underrun/default-engine gates
remain separate. The full-device checklist stays 21/30.

The experiment passes 1,711 tests and 15 parity cases and reduces configuration
publication entries, but the longer watchdog-active row is 0.920x (seven of eight
pairs slower). The implementation, optional native exports and host/package
changes are removed. Eight independent publication-boundary regressions remain.
This protocol is historical evidence, not the next implementation task. Revisit
it only with a materially different design; audit repeated event/deadline scans
next. The current mirror still publishes all 31 bytes.

Manufacturer reference: [ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 5.4 and10–14. It defines register/bus behavior; public host-memory
publication and execution ownership are project contracts, not silicon features.
