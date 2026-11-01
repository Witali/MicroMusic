# ATtiny13A: resolve the pad before delivering its clock

The named digital CLKI fixture shares PB3 among the external source, GPIO,
ADC3 and pin observation. Microchip
[DS40002307A Tables10-2/10-4](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=62)
give PB3 DDOE=0 and PVOE=0. DDRB3/PORTB3 therefore retain control of the output
driver; selecting an external clock is not a blanket output prohibition.
Use manufacturer-derived pin masks and the existing GPIO resolver.

Admit a same-level strong output, including a held clock. On a source event:

```text
settle recognized RESET and release reset GPIO outputs
consume the described external source transition
resolve the shared pad and capture its diagnostic snapshot
if the clock pad has opposed strong drivers: stop with uncertainty
otherwise publish its ADC voltage and deliver source/derived clock phases
```

Apply the same conflict check at GPIO bus writes. A fault must not depend on
the observation mask, selected peripherals or MAIN being gated. CPU registers,
retirement and IRQ stack effects cannot consume the rejected phase. The raw
producer level can differ from the diagnostic GPIO-preferred level after a
conflict; neither establishes a valid opposed-driver voltage. Reinitialization
is required rather than continuing from an invented edge.

RESET needs no CLKI phase to release output drivers. Preapply peripheral reset
before a tied raw edge and let the CPU acknowledge it once. Keep the qualified
RESET receiver and independent watchdog pulse state intact across that
acknowledgment. No host callback or duplicated opcode execution is involved.

This is a correctness technique for the full ATtiny13A C/WASM board, not an
AVR assembly arithmetic backend or a measured speed improvement. The native
module grows by 72 bytes, with unchanged ABI, fixed memory and zero imports.
Opposed-driver electrical behavior, debugWIRE and silicon phase remain open.

The [before/after report](../../web-player/reports/clki-pad-20261101.md) retains
28 scenarios using both held levels, source encodings, CPU/Timer0/ADC3 parity,
exact pins, conflict/completion ordering, reset ties, Power-down and packages.
Two additional checks inspect the analog component's retained PB3 voltage
under both GPIO cache policies, proving that neither bus nor source conflict
publishes the uncertain diagnostic voltage.
The same final source passes 2/28 against the old native artifact and 28/28
against the correction. No firmware profile, browser underrun or physical
accuracy claim follows from those tests.
