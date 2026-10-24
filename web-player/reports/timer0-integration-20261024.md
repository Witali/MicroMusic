# Timer0 uncertainty boundary and probe correction, 2026-10-24

The runtime no longer invents a first-pulse buffer transfer from active TOP=0
to pending OCR0A>0 in phase-correct WGM5. Configuration and a stopped, gated or
edge-free external source remain usable. The next selected timer pulse produces
the existing uncertainty diagnostic before counter, flag, OC or buffer effects.
An internal deadline preserves the last known timer/prescaler prefix on retry.
Non-PWM preload before selecting WGM5 still establishes a supported nonzero TOP.

This corrects an unsupported-behavior boundary. It does not implement or establish
silicon behavior at TOP=0. The relevant manufacturer descriptions and remaining
ambiguity are recorded in the [probe documentation](../native/peripherals/timer0-top-zero-probe.md).

## Regression evidence

The [before/after result](timer0-integration-20261024/before-after.json) uses the
same current generated CPU with the old native runtime from `a4a772a` and the
corrected runtime in `b29e1be`. With active TOP=0, pending OCR0A=3 and source /8,
the old runtime accepted the eighth clock, set TIFR0=14 and executed INC r16.
The corrected runtime reports peripheral fault3/detail6 with r16 and TIFR0 still0.
These are observations of software behavior, not a predicted hardware waveform.

The [exact small harness](timer0-integration-20261024/before-after-source.txt)
can be copied to `build/timer0-uncertainty-before-after.mjs` and run with Node.
The retained native hashes are:

- Before: `9a3461976f84d456ca6f2a1c8b2a24f0b1dadbc85ced2c45d20f1eeffbbc2bde`.
- After: `4adb36626e3151b91147b14a49c7a36ee9709b0da173db9531ed1aa39b5b1210`.

The native boundary fixture covers pending buffers, unchanged flags/OC, delayed
and free-running prescaler phases, repeated faults, CS=0, PRR/TSM/clock gates,
both external polarities, nonzero-TOP prefixes and reset/preload recovery.
Six generated-CPU regressions cover compatible and physical-continuation modes,
including held external T0, the first synchronized edge and uncommitted INC.
The existing9000 timer event-jump differential scenarios still pass.

## Measurement firmware

The original probe swapped T0 and trace clock. Manufacturer TC0/T is PB2; the
serializer now uses PB4. A negative run with source from `28aba01` reproduces
TCNT0=112 before external stimulation: the old boot serializer clocks Timer0.
The new verifier rejects it. A separate GPIO regression checks that PB4 input
and output changes produce no T0 edge while PB2 changes still do.

All12 profiles compile to442–474 Flash bytes, with no initialized data/BSS.
Only the four nonzero controls are executed in software, each with four external
pulses and decoded actual firmware output. The
[verification summary](timer0-probe-20261024.json) retains firmware, official
definitions, native runtime, JS library and generated CPU hashes. A second valid
source with an added comment passes with its own source hash in decoded JSON.
The five Python protocol tests include that alternate-source provenance case.
All software records remain explicitly synthetic; TOP=0 silicon traces are null.

## Verification

```text
node web-player/scripts/build-device-wasm.mjs
node --test web-player/tests/timer0-peripheral.test.mjs web-player/tests/system-gpio.test.mjs
node --test web-player/tests/attiny13a-device-timer0.test.mjs web-player/tests/device-scheduler.test.mjs
python web-player/native/peripherals/timer0-top-zero-probe-test.py
node web-player/scripts/verify-timer0-probe.mjs
node web-player/scripts/generate-attiny13a-registers.mjs --check
node --test web-player/tests/*.test.mjs
```

Use the probe verifier's `--avr-bin`/`--python` options when tools are outside
PATH. The focused Node checks pass51/51 and Python5/5. The
[full-suite summary](timer0-integration-20261024/test-summary.txt) records
1194/1194 passes, no skips or failures, in505752.6ms on this host. This is a test
duration, not an emulator performance measurement. The112642-byte runtime has
no imports,103 function exports plus memory and fixed two-page memory.

The main support checklist remains21/30 complete with nine open. Timer0 TOP=0,
CLKPR/RESET/ADC silicon evidence and other remaining acceptance items are not
closed by these software checks. External virtual-chip programming remains
outside scope.
