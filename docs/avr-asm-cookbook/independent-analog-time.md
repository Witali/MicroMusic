# Keep analog settling separate from delivered CPU clocks

Applicable to MicroMusic's full ATtiny13A C/WASM model and its resumable AVR
emitter, built with Clang 24/Binaryen 133 and Node 22/V8 12.4. This is a
correctness technique; it establishes no speed, code-size or real-time gain.
Runtime arithmetic remains portable C. The separate ADC acquisition firmware
uses AVR assembly with vendor register definitions and AVR GCC7.3.0.

Use independent physical deadlines for an analog comparator's propagation and
reference startup. Use delivered enabled clkI/O rises for digital synchronization
and ACO/ACI publication. Combining both in a count of delivered clock phases
would turn clock holds and CLKPR changes into analog delay changes.

The implemented [explicit ns profile](../../web-player/native/devices/attiny13a/comparator-timing.md)
preserves the old clock-counted fixture as a separately selectable mode. Raw
physical completion precedes a tied modeled clock edge; ordinary input mutation
at that timestamp follows the edge. Account for ceil-to-ps quantization rather
than assuming a delivered edge has zero rational remainder. Initial-low CLKI
also needs explicit first-edge delivery because its aligned half counter can
still be zero. Do not advance that counter artificially to force sampling.

[Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
section 13.2.2 and Table 18-7 distinguish analog ns delay from digital CLK delay;
the exact values depend on input and supply conditions. Tests use explicit
synthetic parameters and compare exact/adjacent boundaries, not guessed silicon
calibration. The [retained evidence](../../web-player/reports/comparator-physical-20261026.md)
records tests, source/runtime identities and default-mode active-IRQ output parity.

An additional [independent BigInt phase oracle](../../web-player/tests/attiny13a-comparator-osccal.test.mjs)
checks 3574 scenarios in eight groups: positive/negative OSCCAL changes,
pending propagation/reference startup at CLKPR /1 and /8, quantized edge ties,
zero-delta service and held external CLKI. It derives expected deadlines without
production timing helpers. All eight groups pass; these checks validate the
selected digital convention and do not measure silicon oscillator settling.

Reference enable is a separate shared resource. Keep an owner mask for ADC,
software ACBG/ACD and BOD, retain one physical startup across continuous owner
handoffs, and qualify loss of power using current POR rather than aggregate
RESET or sticky flags. Automatic peripheral clock gating need not release its
analog request. Publish readiness before a tied sample without advancing the
consumer during publication. The [implemented shared profile](../../web-player/native/devices/attiny13a/shared-reference.md)
keeps BOD recovery independent and diagnoses unavailable ADC samples. Explicit
startup fixtures and generated-CPU lifecycle tests validate the selected digital
contract; they establish no calibrated analog startup or performance benefit.

An independent manufacturer's simulator is useful only within its documented
coverage. Microchip Studio excludes analog modeling and has incomplete NVM
behavior; instruction-boundary stimuli also cannot prove subinstruction pad
timing. The [official-host acquisition record](../../web-player/native/devices/attiny13a/simulator-oracle.md)
pins the signed installer/payload provenance, supported automation and these
limits. Downloaded host files and successful CLI help are not an executed
simulator comparison or an analog oracle.

For an ambiguous sleep-start condition, keep the observation independent of its
interrupt. The [ATtiny13A ADIE probe](../../web-player/native/peripherals/adc-sleep-probe.md)
uses an unrelated watchdog wake, raw result/ADIF and both ISR counts/order.
Serialization starts after evidence is frozen, and vector acknowledgement is
accounted for explicitly. Paired controls validate the acquisition without
assigning an unmeasured silicon result. This is measurement-tool correctness,
not a runtime optimization or a claim that the ambiguity has been resolved.
