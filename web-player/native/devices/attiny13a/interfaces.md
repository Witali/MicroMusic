# External interfaces: implementation inventory

Audit date: 2026-10-23. This inventory describes the current software boundary;
loading a firmware package does not implement a programming or debug transport.

| Interface | Current boundary | Work required for physical support |
| --- | --- | --- |
| CLKI on PB3 | Timestamped physical source edges clock the board through CKDIV8/CLKPR; bounded CPU/IRQ continuations preserve progress through holds, startup and sleep | The named digital phase policy is implemented; pad timing, analog clock reception and silicon phase measurements remain open |
| External RESET | Optional analog PB5 receiver feeds the reset aggregator; digital injection stays prequalified | Supply and receiver parameters are explicit profiles; silicon calibration/measurement remains open |
| ISP | Excluded by the user's scope decision | No programmer or command transport is planned |
| HVSP | Excluded by the user's scope decision | No programming backend, HV entry or wire receiver is planned |
| debugWIRE | Diagnostic BREAK support is controlled by the host option; DWDR has no debugger channel | Documented DWEN pin mux/reset effects and a debugger state contract; a wire implementation requires an authoritative protocol source |

All existing native peripheral sources implement ATtiny13A; the shared AVR
emitter and generated firmware have separate ownership. Other chips require
their own device sources and an explicit build selection rather than
additional names on the ATtiny13A implementation. This audit lives under the
device-specific directory.

## Clock and reset constraints

The [CLKI implementation](clki-design.md) uses physical picoseconds and real
queued transitions rather than a configured average frequency. WDT, supply
events and NVM wall latency continue while CLKI is held high or low. CPU/IRQ
effects wait for their remaining delivered phases. Startup combines source CK
with an independent watchdog timeout. PB3 is the same pad observed by GPIO,
ADC3 and pin capture; separate PB3 injection and output contention are rejected
in this fixture rather than inventing a DDRB3 override.

Arbitrary batches and finite exact periodic descriptors feed a bounded native
edge queue. Periodic descriptors refill it lazily in C, with no per-edge JS
callback. Each externally observable source edge is still serviced. A declared
edge-free interval means a known hold; exhausting the published input horizon
returns `WAIT_INPUT` without extrapolating a period. The optional
`datasheet-ideal-v1` validator checks ideal digital timing limits, not analog
receiver behavior or measured silicon phase.

The RESET pulse requirement is not a published exact assertion delay. Typical
voltage and hysteresis plots do not provide a universal receiver transfer
function. The optional [analog receiver](reset_input.md) has separate threshold,
qualification and propagation choices. The prequalified digital API bypasses
that receiver. RESET-specific characteristics are distinct from PB5 GPIO plots.

The board uses the receiver's next physical deadline, preserves it through CPU
reset acknowledgement and combines its output with POR/BOD/WDT and the digital
bypass. The generated CPU, native audio collector and package v5 path use
the same model; no host callback handles individual voltage transitions.
Package v4 is the historical RESET-receiver format; v5 also records the optional
resumable execution and CLKI profiles.

## Debug and programming constraints

The datasheet describes DWEN, open-drain PB5, BREAK and DWDR, but the retained
manufacturer pack supplies no debugWIRE framing, commands or wire timing.
Its `interface=dw`, `OCD_REVISION=0` and `OCD_DATAREG=0x2e` metadata do not define
a protocol. A semantic debugger API must identify itself as such.

There is also a documentation conflict: section17.1 warns that debugWIRE can
read locked Flash, while Table17-2 and section15.3 say lock bits disable it.
Do not silently derive a complete DWEN/RSTDISBL/lock truth table from one of
these statements. Record unsupported combinations until a selected profile or
manufacturer clarification resolves them.

External-chip programming is outside the current plan. The virtual device
starts directly from its supplied firmware and memory image. No ISP/HVSP
backend is retained; those interfaces are not missing acceptance tasks. See
[`EMULATION_SCOPE.md`](../../EMULATION_SCOPE.md) for the explicit scope decision.

## Primary references

- [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf): sections6.2.1,8.2.2,15,17; Tables6-3,10-4,18-3,18-4; Figures19-55 through19-58.
- [Pinned Microchip device pack](../../../vendor/microchip/ATtiny_DFP/3.4.278/README.md): exact device definitions, debug metadata and provenance.
- [Microchip DS80000857A](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/Errata/ATtiny13A-SilConErrataClarif-DS80000857A.pdf): EEPROM voltage erratum; no debugWIRE protocol clarification.
