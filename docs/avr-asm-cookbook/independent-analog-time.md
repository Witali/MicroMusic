# Keep analog settling separate from delivered CPU clocks

Applicable to MicroMusic's full ATtiny13A C/WASM model and its resumable AVR
emitter, built with Clang 24/Binaryen 133 and Node 22/V8 12.4. This is a
correctness technique; it establishes no speed, code-size or real-time gain.
No handwritten assembly or architecture-specific arithmetic backend is added.

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
