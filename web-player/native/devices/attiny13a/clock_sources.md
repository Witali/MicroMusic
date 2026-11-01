# Physical low-power clock source

[Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
figure 6-1 and sections 6.2.3/8.4, show the watchdog oscillator feeding both WDT
and the clock multiplexer. CKSEL11 selects this source for the CPU. Its nominal
frequency is 128 kHz; an explicit fixture or measured profile may provide a
different actual rate. These consumers must use the same source frequency.
CLKPR/CKDIV8 divide the synchronous CPU/Timer0 domain, not the WDT input.

In physical mode (`osccalHz` supplied), `oscillatorHz` must therefore equal
`watchdogHz` for CKSEL11. Native initialization rejects a mismatch with config
fault 1/detail 18 before touching caller memories. The runtime constructor and
portable package validator share a device-owned check. This also protects
packages with historical runtimes: versions 2–7 are checked before executing
the embedded runtime. No package fields or ABI exports change.

For example, a nominal divided low-power fixture uses:

```js
{
  fuseLow: 0x63,                 // CKSEL11, CKDIV8 programmed, SUT00
  oscillatorHz: 128000,
  watchdogHz: 128000,
  osccalHz: explicitCalibrationTable,
  resumable: true
}
```

The existing explicit RC calibration-table contract remains in force. This
change does not infer that curve, alter OSCCAL handling, automatically choose
which contradictory frequency was intended, or change the legacy independent-
clock digital fixture. Previously accepted physical CKSEL11 packages with
different rates must be corrected to one consistent rate.

The correction validates source identity/frequency. It does **not** determine
the undocumented internal phase relationship at reset, oscillator analog
startup or a measured electrical accuracy. Existing phase/startup conventions
and hardware-validation tasks remain. Equal-rate admission alone cannot prove
the verification model's 10 ns event-timestamp requirement against silicon.

Regression evidence includes rejection at native/runtime/package boundaries,
untouched memories on failed init, successful retry, non-CKSEL11 controls,
and a shared-source CKDIV8 test: 256 CPU/Timer0 cycles consume 2048 source cycles
and reach the first WDT timeout at 16 ms for the explicit 128 kHz fixture.
A resumable NOP image and its package reload retain exact state/timing after
an inactive-RC OSCCAL write. See the
[validation report](../../../reports/low-power-clock-20261101.md).
