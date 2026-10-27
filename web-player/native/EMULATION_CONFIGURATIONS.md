# Verification and site configurations

Model selection is separate from the JS / WASM / AVR → WASM CPU backend.
Select **Модель эмуляции** on the player, or use `?emulation=verification`.
The default remains `site` with the WASM backend. Changing configuration resets
the firmware/audio stream; the Worker retains the choice when attaching a new
audio port. Returning to site mode restores the previously selected backend.

| Configuration | ATtiny13A | ATtiny88 |
| --- | --- | --- |
| `site` | Existing music-oriented CPU/Timer0 model with observed PWM values and resampling. | Existing shared CPU/Timer1 music model. |
| `verification` | Full native device board, generated CPU with resumable instruction phases, integer physical time and integrated physical pin audio. | Shared core/Timer1 reference with wait-loop and native block skipping disabled. Full Tiny88 peripherals are still unavailable. |

For Tiny13 verification, the supported backend is AVR → WASM (`device` remains
an API alias). The UI selects it and disables incompatible backend choices.
An explicit API request for the simplified JS/native WASM backend in this mode
fails instead of silently selecting a weaker model. All three backends remain
available for Tiny88's limited reference configuration.

The verification execution policy disables wait skipping and flag elimination,
uses two-instruction maximum basic blocks, and leaves bounded regions and
phase-local optimizations disabled. Verified peripheral deadline caches still
preserve their exact event boundaries; this is not a second copied device
implementation. The site profile retains its existing fast paths and supported
subset. Its musical output and full supported CPU/timer state remain covered
by the existing differential tests.

Full ATtiny13A catalog construction can reuse verified generated WASM from a
[bounded persistent cache](../lib/avr-persistent-cache.README.md) across Worker
restarts. Every instance starts with fresh CPU/peripheral memory and queues.
This preserves the selected hardware and conservative verification policy;
site engines and packaged-runtime loading retain their existing paths.

## Verification virtual-event tolerance

User clarification, 2026-10-27: the full ATtiny13A verification simulator requires
virtual CLK, timer and pin-event timestamps within **10 ns (10,000 ps)** of the
corresponding reference event. This is a maximum per-event error across the
whole compared trace, not an allowance to accumulate 10 ns on every clock step.

The tolerance applies only to the precise verification model. It introduces no
new accuracy requirement for the simplified `site` music model, audio sample
spacing, browser wall-clock scheduling or host performance profiling. Existing
integer-picosecond representation remains valid; this does not require rounding
events onto a 10 ns grid.

Event identity, event count, original CPU-cycle counts, register/flag effects
and the required ordering of tied or neighboring events remain exact. Matching
timestamps within tolerance cannot excuse a lost edge, duplicate IRQ or changed
read/write ordering. Compare equivalent inputs, fuses and explicit hardware
profiles; distinguish model timestamp error from instrument uncertainty and
unmeasured oscillator/analog behavior. The tolerance alone does not establish
silicon calibration or close the outstanding hardware checks.

The [acceptance replay](../scripts/verify-virtual-event-accuracy.mjs) applies this
bound to the real full model using analytical clock/Timer0/firmware pin fixtures.
Its [recorded software evidence](../reports/virtual-event-accuracy-20261027.md)
keeps exact event/state comparisons separate from unmeasured silicon accuracy.

## Historical evidence

The full model was retained, not replaced by the music model:

- `e9be78bc` (2026-10-23): calibrated clocks and PWM capture on integer physical time.
- `f49a78a3` (2026-10-23): resumable generated AVR instructions across physical deadlines.
- `801b7fd6`: connected bounded external CLKI streams.
- `1c2172d2` (2026-10-24): shared Tiny13/Tiny88 music-core profiles.
- `5b2e6fda`: Tiny88 translation and three player backend choices.

The current full board stays in `native/peripherals/` and
`lib/attiny13a-runtime.js`; the site model stays in the profile-aware
`native/avr.c` / `lib/avr-reference.js`. No historical native binary was restored
and no previously rejected performance experiment was reintroduced.

## API and explicit hardware profiles

```js
import {createRenderer} from './lib/engines.js';
const site = await createRenderer(entry, 48000, controls, 'wasm', 'site');
const check = await createRenderer(entry, 48000, controls, undefined, 'verification');
// check.configuration / check.emulationModel identify the actual selected model.
```

For ordinary catalog images, full-board verification uses the declared nominal
CPU rate, factory CAL=0 with only that OSCCAL point specified, the player's
0x7A fuse profile and fuse startup timing. This is a nominal test fixture, not
a measured oscillator curve. Unknown OSCCAL changes fail explicitly. No analog
threshold, comparator delay, power/RESET qualification or uncertain silicon
behavior is invented by this preset. For measured-clock, RESET/supply or CLKI
experiments, keep the explicit device inputs and apply only execution policy:

```js
import {ATtiny13A} from './lib/attiny13a.js';
import {executionOptions} from './lib/emulation-configurations.js';
const check = new ATtiny13A(flash, eeprom, {
  ...measuredDeviceOptions, ...executionOptions('verification'), resumable: true,
});
```

Packages always preserve their embedded native runtime and hardware settings,
including in site mode: they are never silently downgraded. Verification
requires an already resumable physical-clock package, checks its ABI/integrity,
then recompiles the supplied image with the verification CPU policy. Older
compatible-clock packages remain playable in site mode and receive an explicit
error in verification mode. The standalone JS loader now also includes
`emulation-configurations.js`; no default WASM download is introduced.

Full-device verification is the most detailed available digital model, not a
claim of complete silicon validation. Remaining seven ATtiny13A checklist items,
including hardware measurements, stay open. Virtual ISP/HVSP/programmer
interfaces remain excluded. See [scope](EMULATION_SCOPE.md),
[the support plan](ATTINY13A_PLAN.md), [the simplification plan](MODEL_SIMPLIFICATION.md)
and [the existing model choices](AVR_TO_WASM.md).

## Validation checkpoint, 2026-10-26

All 1848 player tests and 61 shared music-core/startup tests pass, with no
failures or skips. This includes the two new configuration APIs, physical
partial-instruction stops, physical audio block partitioning, Tiny88 output/IRQ
parity, package policy/integrity, UI mode/URL/backend restoration, and the real
Worker's queued controls and audio-port recreation. Commands:

```text
node --test web-player/tests/*.test.mjs
node --test tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs
```

The in-app browser also exercises the real Worker/AudioWorklet: Tiny13 physical
verification executes the stereo Lumiere image, then mode switching restores
site/WASM. Tiny88 verification displays its peripheral limit. The inspected
12.2 seconds of physical execution show 117964800 CPU cycles, 458398 IRQs and
zero lost IRQs, but 59 audio underruns while the full test suite was also
running. This is functional evidence only; verification mode has no real-time
audio acceptance claim. The screenshot stays in ignored
`build/emulation-config-verification.png`. No native WASM, firmware or vendor
definition bytes change in this configuration split.

Plan reconciliation: explicit verification/site delivery closes the updated
delivery criterion, replacing the former full-model website default as requested
by the user. The count is22/30, eight open; hardware/performance requirements are
unchanged. The subsequent ADC sequencing correction `9b9015b4` passes1919
default/shared-tool checks and rebuilds only the full-device native runtime.
The browser observation above belongs to the earlier configuration split.

Latest software checkpoint: the optional incremental compiler/dynamic linker
and persistent cache close the caching criterion, bringing the plan to23/30,
seven open. This does not enable a faster default, close hardware uncertainties
or imply real-time support; see [the linking contract](INCREMENTAL_COMPILATION.md).
