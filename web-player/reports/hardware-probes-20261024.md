# ATtiny13A acquisition probes, 2026-10-24

Three source-only acquisition programs now cover CLKPR switching, physical RESET
and the two documented ADC ambiguities. All use pinned manufacturer register
definitions and the common wire-v2 sender. No silicon observation, calibration
curve, default-model change or virtual programming interface is supplied.

## Build and integrated software controls

The [verification data](hardware-probes-20261024/verification.json) retains
source/config/sender/decoder/definition hashes, native and complete JS library
identities, compiler version, image and generated CPU hashes, raw decoded fields
and synthetic waveform hashes.

| Program | Profiles | Flash bytes | Decoded frames |
|---|---:|---:|---:|
|CLKPR|12|602–614|24|
|RESET|4|204|8|
|ADC|9|278–286|27|

All25 images have zero data/BSS sections and use at most four bytes of nested
return storage. The generated CPU executes each actual binary with the native
board and finite continuous external CLKI descriptors. Output is collected in
bounded slices and decoded by the Python protocol checker, not replaced by host
register writes or invented transport data.

CLKPR checks both steady divisors from actual OC0A edge intervals, uninterrupted
source phases, both serialized snapshots, the marker bracket and ignored/unlocked
write controls. The transition's hidden silicon ripple phase remains unmeasured.

RESET checks all four SUT/CKDIV8 profiles, first POR and second EXTRF boot causes,
initial divider, released PB0 driver during reset and post-frame heartbeat. Its
test reset is prequalified digital input. It does not measure analog thresholds,
pad RC or actual watchdog oscillator duration.

ADC checks the correct ADC1/PB2 path at ideal1V/VCC5V, both trial results, captured
status/SREG, and documented whole-byte flag controls. SBI/CBI ADIF observations
remain software-policy results, not a resolution of the data-sheet conflict.

## Aperture discrimination

The [sensitivity data](hardware-probes-20261024/adc-aperture-sensitivity.json)
retains40 runs/80 actual trial records, byte frames/checksums, both marker edges,
future queued injections and exact input/code identities. The first-conversion
probe ran under `adcFirstSample:27` and29, with source8MHz, ADC/64, ideal1V↔4V
steps, explicit5V and watchdog128kHz software parameters. Normal warmed controls
were tested separately. All results come from serialized ADCL/ADCH bytes.

Representative results below are the same in both measured trials per run:

| Profile / step direction | Delay from marker | Code at27 | Code at29 |
|---|---:|---:|---:|
|First / rising|112us|819|819|
|First / rising|120us|204|819|
|First / rising|126us|204|204|
|First / falling|112us|204|204|
|First / falling|120us|819|204|
|First / falling|126us|819|819|
|Normal / rising|120us|204|204|
|Normal / falling|120us|819|819|

The distinguishing tested offsets are118,120,122,124us. An assumed112us delay
would not distinguish this fixture. This establishes that the assembled probe
can observe the configured difference, and that its normal control is insensitive
to the first-sample choice. It establishes no actual silicon aperture, preferred
default, analog settling/noise response or universal offset from GPIO to ADC.
Physical acquisition must sweep measured input transitions and compare bounded
completion/aperture intervals, as described in [the ADC procedure](../native/peripherals/adc-probe.md).

## Reproduction and remaining work

```text
python web-player/native/peripherals/hardware-probe-test.py
python web-player/native/peripherals/timer0-top-zero-probe-test.py
node web-player/scripts/generate-attiny13a-registers.mjs --check
node web-player/scripts/verify-hardware-probes.mjs
node web-player/scripts/verify-adc-aperture.mjs
```

Use `--avr-bin`/`--python` when tools are outside PATH. Protocol tests pass15/15;
the existing Timer0 wire-v1 checks pass5/5. Actual generated frames validate all
new wire-v2 encoders. Partial RESET frames have explicit diagnostic recovery,
not silent skipping. Original vendor files remain byte-identical. The pinned
ATDF's missing CLKI/RESET and PAx ADC aliases are documented separately from
the data-sheet pin adaptations.

Production CPU, peripheral runtime and library files are unchanged. Native WASM
remains112642 bytes, SHA-256
`4adb36626e3151b91147b14a49c7a36ee9709b0da173db9531ed1aa39b5b1210`.
The1194/1194 full-suite result belongs to the preceding Timer0 integration;
this tooling change uses the focused protocol and actual-image controls above.

All retained new traces are explicitly synthetic/unreviewed. Hardware captures,
conditions and uncertainty analysis are still needed. The broader CPU internal
bus/stack-phase hardware audit also remains open; these three programs do not
replace it. The main plan remains21/30 complete with nine open acceptance items.
