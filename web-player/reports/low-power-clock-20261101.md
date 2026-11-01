# One frequency for the physical CKSEL11 source

The precise ATtiny13A model accepted contradictory CPU-source/watchdog
frequencies even though CKSEL11 selects the watchdog oscillator itself. Native
initialization, public runtime construction and package validation now reject
that configuration. The device-owned JS check is shared by both host paths;
native init protects direct WASM callers and leaves caller memories untouched
on rejection. A corrected profile can initialize successfully afterward.

The [source contract](../native/devices/attiny13a/clock_sources.md) links the
official clock-distribution diagram and explains the distinction between the
undivided source and CKDIV8/CLKPR. Legacy independent-clock fixtures retain their
existing behavior. Physical-capable package versions 2–7 are checked, including
packages with older runtime binaries; no format or ABI extension is introduced.

## Verification

Three new boundary checks reproduced the missing admission check before the
fix. All **51 focused checks** now pass. Controls preserve independent rates
for the other source selections and the legacy fixture. The valid low-power
test verifies the WDT flag at exactly 16 ms for the explicit 128 kHz source,
while CKDIV8 has delivered only 256 CPU/Timer0 cycles. A resumable NOP image
and its package reload preserve complete state and timing after an OSCCAL
write that does not select the inactive calibrated RC source.

The first full run found one failure: the isolated loader test's copied-file
list omitted the new JS module. The dependency was added without weakening
its assertions; all twelve package-runtime checks then pass. The final full
suite passes **2659/2659**, with no skips or failures. Its TAP hash is recorded in the
[JSON evidence](low-power-clock-20261101.json).

The native module grows from 124614 to **124684 bytes**. Its new SHA-256 is
`4ccbce15195e10c625737c42e2e7aa5660dd8b3374126771fc97efb460267416`.
An isolated rebuild is byte-identical. Compiler flags, 17 C sources, 117
function exports, no imports, fixed two-page memory and resumable ABI remain
unchanged. The loader URL and 41-source compiler/cache identity are updated.
The retained manifest and evidence bind every native/host/test input.

This corrects source-frequency consistency. It does not establish the internal
source-to-WDT phase at reset, electrical oscillator accuracy, measured CLKPR
transition behavior or the silicon 10 ns acceptance gate. No execution-speed
claim is made. The plan stays **24/31 complete, seven open**.

## Reproduction

From the repository root, with the already registered SDK:

```text
node web-player/scripts/build-device-wasm.mjs --out-dir build/low-power-clock-rebuild-20261101
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/device-low-power-clock.test.mjs web-player/tests/device-osccal-runtime.test.mjs web-player/tests/attiny13a-package.test.mjs
node --test web-player/tests/attiny13a-package-runtime.test.mjs
```

Run the complete default suite with `npm test` from `web-player`. Raw before,
focused, first/final full and loader TAPs remain under ignored `build/`; only
counts/hashes are retained in Git. The pinned datasheet/definitions/toolchain
are reused. No software was downloaded or installed for this correction.
