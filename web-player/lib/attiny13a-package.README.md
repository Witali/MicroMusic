# ATtiny13A package format v5

`attiny13a-package.js` creates and verifies a self-contained initial device image.
It has no Node imports and uses asynchronous WebCrypto SHA-256, so the same
module works in Node 22 and browsers in a secure context. It never constructs
a `WebAssembly.Instance`.

```js
import {createPackage, decodePackage, assertPackageRuntimeABI}
  from './attiny13a-package.js';

const pkg = await createPackage({
  flash, eeprom, configuration, translated, runtime, manifest,
});
const savedJSON = JSON.stringify(pkg);
const decoded = await decodePackage(savedJSON);
// decoded: flash/eeprom/translated/runtime Uint8Arrays, configuration, options,
// manifest, abi and integrity. options is a separate configuration copy.
```

`flash` contains 1–1024 bytes and is padded to 1024 with `0xff`. Optional
`eeprom` must contain exactly 64 bytes; omission creates an erased image.
`translated` and `runtime` are WASM bytes. Optional `manifest` must equal the
translation's embedded `micromusic.avr` manifest. No files or URLs are referenced
by the saved package.

The envelope identifies format `micromusic-attiny13a-package`, version `5`,
device `ATtiny13A`, and ABI `micromusic-attiny13a-device-v1`. Each of the four
binary assets records its length, canonical base64 and SHA-256. The envelope
hash covers all fields except `integrity`, including configuration, manifests
and asset hashes. Hash input is UTF-8 JSON with recursively sorted object keys,
preserved array order and standard JSON scalar encoding. Pretty-printing or
object key order does not change integrity.

The JavaScript loader includes `avr-profiles.js` alongside `avr-runtime.js`;
this shared profile metadata does not load a default WASM artifact. Historical
packages retain their own runtime memory layout and decode-operand width.

The loader rejects unsupported identities, missing/unknown envelope fields,
invalid configuration, noncanonical base64, changed bytes/hashes, inconsistent
Flash instruction words, differing embedded/outer manifests and incompatible
WASM interfaces. It verifies fixed unshared wasm32 memory, the full-device
function signatures, no runtime imports, only expected translation imports,
and no WASM start section. Both binaries must pass the engine's validation.
Limits are 1024-byte Flash, 64-byte EEPROM, 4 MiB translation, 2 MiB runtime,
512 KiB embedded manifest and 16 MiB JSON. These are format limits, not device
performance promises.

The decoder also accepts versions 1, 2, 3 and 4 with their original configuration and
runtime contracts. Version 2 added the physical-clock bridge and calibration
profile. Version 3 added the optional supply profile and its bridge exports.
Version 4 added an optional analog RESET input profile and four receiver bridge
exports. Version 5 adds `resumable:false` and `clkiProfile:null`; historical
versions omit both fields and retain their earlier execution/import contracts.
Historical versions do not require these new fields or exports;
retained original v1/v3 runtimes exercise that compatibility.
Resumable translations declare `executionMode:'resumable-v1'`, an80-byte `phase`
context in the ABI, and three additional imports: `phaseClock(f64)->i32`,
`phaseDeadline(f64)->void`, `phaseRetire()->void`. The loader validates context
field alignment, bounds and nonoverlap with each other and the other ABI regions,
matching execution mode/configuration, and native phase enable/layout/active
signatures. Nonresumable translations retain the earlier import set.
The original v1 runtime lacks three later configuration keys and four state
observers. Its loader accepts only the historical defaults for unsupported keys
(60000ns BOD recovery, factory CAL0, zero-delay startup); unsupported nondefault
values are rejected. Missing state observers report inactive startup/BOD state.

SHA-256 detects corruption and inconsistent components. An author can modify
code and recompute its hashes. This is not a signature, a trust decision, or a
proof that the translated machine code implements the supplied Flash. Loading
unknown packages still means loading executable WASM.

The declared C data layout cannot be inferred from arbitrary WASM function
bodies without executing them. After verifying the package, the integrating
loader must instantiate its runtime and call
`assertPackageRuntimeABI(decoded, runtimeABI(runtimeInstance.exports,
{resumable:!!decoded.options.resumable}))` before
constructing the translated instance. This checks the live state offsets,
memory regions and device marker against the translation. The package API
does not instantiate the device, change default engine selection, or fetch an
external runtime.

## Execute in the player

`ATtiny13A.fromPackage(json)` verifies the package, instantiates its runtime,
checks the live ABI, then binds the supplied translation. Later self-programming
uses the normal Flash-generation invalidation and retranslates the modified
image. Import `ATtiny13A` from `attiny13a-runtime.js` to load a package without
fetching either default WASM image. The usual `attiny13a.js` entry point also
exposes this method and supports ordinary Flash construction.

The player opens packages through **Открыть пакет ATtiny13A**. Imported packages
use the full device engine and show PB0/PB1 as stereo output. The package's fuses,
oscillator and initial memory are used as saved. Programmatic worker entries
use `{devicePackage: pkg, audioChannels: 1|2}`; mono observes PB1, stereo observes
PB0 then PB1. Audio observation settings are host choices, separate from the
initial device state.

## Reproducible configuration

All configuration keys are stored, including defaults. Unknown keys are
rejected. This represents the configured deterministic digital/analog profile;
it does not assert complete silicon behavior or measured oscillator calibration.

| Fields | Default | Accepted values |
|---|---:|---|
| `oscillatorHz` | 9600000 | integer 1–1000000000 |
| `watchdogHz` | 128000 | integer 1–1000000000 |
| `vccMicrovolts` | 5000000 | integer1–2147483647;0 only with an explicit supply profile |
| `bandgapMicrovolts` | 1100000 | integer 1–2147483647 |
| `fuseLow`, `fuseHigh`, `lock` | 122, 255, 255 | integer 0–255 |
| `adcFirstSample` | 27 | 27 or 29 (half ADC periods) |
| `comparatorPropagationHalf`, `bandgapStartupHalf` | 0 | uint32, runtime half-clock domain |
| `comparatorInitial` | 0 | integer 0 or 1 |
| `wakeStartupHalf` | 0 | uint32, base half ticks; even for CLKI's explicit source-CK count |
| `spmCommandCycles` | 0 | uint32; 0 keeps missing timing explicit |
| `flashMaximum` | 1 | integer 0 or 1 |
| `bodRecoveryNs` | 60000 | uint32, nanoseconds |
| `factoryOsccal96` | 0 | integer 0–127, caller-supplied fixture byte |
| `fuseStartupProfile` | 0 | integer 0 or 1 |
| `osccalHz` | null | null, or128 integer frequencies0–1000000000;0 means unspecified |
| `nvmClockProfile` | 0 | 0 unspecified,1 explicit fixed-nanosecond programming fixture |
| `nvmCalibrationReferenceHz` | 0 | 0 unspecified, otherwise1–1000000000 |
| `powerResetProfile` | null | null, or the complete explicit profile below |
| `resetInputProfile` | null | null, or the complete six-field RESET receiver profile below |
| `resumable` | false | boolean; optional CPU continuation mode, requiring physical time |
| `clkiProfile` | null | null, or the exact digital fixture described below |

A non-null `osccalHz` table selects a physical picosecond clock domain. Its
factory CAL entry must be supplied and, for the internal calibrated RC source,
equal `oscillatorHz`. Other selected clock sources keep their configured
frequency when CAL is written. An unlisted CAL write fails explicitly for the
internal calibrated RC source.
The table is supplied by the caller; no universal CAL/frequency curve is implied.
`nvmClockProfile:1` requires a nonzero calibration reference and explicitly keeps
the selected programming durations fixed in nanoseconds. With profile0,
programming in the variable-clock model requires a timing profile first. This
fixture does not claim the silicon's undocumented CAL/programming-clock relation.

For this clock domain, use `runUntilPs(bigint)`, `injectPinsPs`, `setAnalogPs`
and `drainPinsPs`. `state()` exposes `timePs`, `startupDeadlinePs` and the current
`oscillatorHz`. Input and output timestamps are unsigned64-bit picoseconds.
The original methods retain their oscillator-half unit for the fixed-clock
profile. Mixing the two domains fails before advancing the device.
Physical audio capture keeps its sample grid independent of CAL and CLKPR.
Its native WASM execution uses relative deadlines per host batch while storing
absolute time as integers, preserving precision beyond2^53 picoseconds.

The optional power profile requires physical time (`osccalHz` or `clkiProfile`) and all nine fields:
`porAssertMicrovolts`, `porReleaseMicrovolts`, `bod00Microvolts`,
`bod01Microvolts`, `bod10Microvolts`, `bodHysteresisMicrovolts`, `bodFilterNs`,
`bodRecoveryNs` and `flashProgrammingMinMicrovolts`. Thresholds are positive
int32 microvolts, hysteresis is nonnegative int32, and both durations are uint32
nanoseconds. POR release must be at least the assertion threshold; each BOD
center plus/minus its half-hysteresis must fit the supported voltage range.
No analog thresholds are supplied as hidden defaults. See
[`device-power.md`](../native/peripherals/device-power.md) for the exact digital
qualification, reset aggregation, sleep and programming contracts.

The optional `resetInputProfile` requires physical time (`osccalHz` or `clkiProfile`) and DWEN
unprogrammed. It has exactly six fields: `assertThresholdPpm`,
`releaseThresholdPpm`, `assertQualificationNs`, `releaseQualificationNs`,
`assertPropagationNs` and `releasePropagationNs`. Thresholds satisfy
`200000 <= assert < release <= 900000`; durations are uint32 nanoseconds,
including zero. There are no hidden receiver defaults.

`setAnalogPs({at,pin:5,microvolts})` supplies the RESET pad voltage. Until
selected, its receiver voltage follows VCC. Thresholds track current VCC, with
explicit hysteresis and two inertial timing stages. `injectPinsPs` remains a
prequalified digital RESET bypass. RSTDISBL gates the pin's reset role. A supply
profile is only needed when changing VCC, rather than for a fixed supply.

`state()` exposes `resetInputEnabled`, `resetInputAsserted` and
`resetInputDeadlinePs` when this profile is enabled. Recognition runs in native
WASM, contributes to the scheduler's minimum deadline and feeds shared reset
hold/startup without per-edge JS calls. For the selected model and manufacturer
limits see [`reset_input.md`](../native/devices/attiny13a/reset_input.md).
The preserved original v3 runtime predates this receiver; only a v4 or later package
may carry its profile.

With this profile, initial `vccMicrovolts` may be zero. Queue supply changes with
`setVccPs({at: bigint, microvolts})`. They share chronological ordering with pin
and analog inputs. `state()` adds `powerResetEnabled` and current `vccMicrovolts`.
The observer survives CPU reset. The selected power-profile `bodRecoveryNs`
overrides the older flat recovery setting while enabled. An EEPROM programming
operation below 1.9V, or Flash programming below the explicit selected boundary,
stops with an uncertainty diagnostic and preserves the last known bytes instead
of committing an invented result. The package remains an initial image, not a
snapshot of in-flight operations or queued external inputs.

## Resumable CPU and digital CLKI stream

`resumable:true` enables instructions to stop at a physical deadline and resume
their latched operands/read results and stack phases on the next `runUntilPs`.
The supplied translation must have the matching execution mode and phase ABI.
Internal oscillator use still requires an explicit `osccalHz` table.

The only accepted external fixture is
`clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:0}`
(or initial level1). It requires `resumable:true` and CKSEL00 (`fuseLow&3===0`).
This profile selects physical time independently of `osccalHz`; no dummy
calibration table or predicted clock period is needed. It is a logical input
fixture with a named initial/divider phase, rather than a measurement of silicon
phase. Packages using it must supply the complete native CLKI bridge
with the checked signatures. A package stores the initial profile, not a saved
edge queue, periodic descriptor or continuation. ISP/HVSP transport is outside
the runtime's scope; loading the image does not execute a programming protocol.

Raw constructor/writer input may additionally select
`electricalValidation:'none'|'datasheet-ideal-v1'`. Omitting it means `none`;
the saved v5 profile always includes this third field. The optional ideal-digital
qualification assumes zero slew and checks the selected datasheet voltage tier's
period/high/low minima and both period/frequency interpretations of the2% rule.
It is not an analog receiver or measured-clock guarantee. Enabling it requires
the native runtime to accept CLKI configuration field2; unsupported runtimes
reject the profile during initialization rather than silently disabling checks.

Submit edges with
`injectClkiPs({edges:[{timePs:100000n,level:1}],knownUntilPs:200000n})`.
Timestamps are uint64 picoseconds, excluding UINT64_MAX. The inclusive known
horizon cannot move backward; new alternating edges must be strictly later
than the previously published horizon and lie within the new horizon. An empty
batch extends a known high/low hold. The host validates the batch, copies it into
a bounded512-edge staging buffer, and commits once in C/WASM. `false` reports
backpressure without accepting a partial batch or horizon; malformed input
throws. There are no per-edge JS callbacks while executing the CPU.

A finite exact periodic descriptor avoids constructing a large JS edge array:

```js
const cpu = new ATtiny13A(flash, eeprom, {
  fuseLow: 0x78, // CKSEL00, CKDIV8 unprogrammed: divide by one
  resumable: true,
  clkiProfile: {
    phasePolicy: 'digital-noninverting-zero-seed-v1', initialLevel: 0,
  },
});
cpu.injectClkiPeriodicPs({
  startPs: 0n, initialLevel: 0,
  highPs: 40_000n, lowPs: 60_000n,
  transitionCount: 20_000n, knownUntilPs: 1_200_000_000n,
});
const rawPCM = cpu.capturePhysical(48, 48_000, 1); // native pin integration
cpu.runUntilPs(1_200_000_000n); // known low hold after the final edge
```

All descriptor timestamps, durations and counts are BigInt uint64 values;
durations are positive. The start must be at or after the old horizon and its
initial level must match the already-declared tail. The first transition is
`startPs + (initialLevel ? highPs : lowPs)`; start itself creates no edge.
Transitions alternate using exact integer durations, without Hz rounding or a
fractional-duration option. The final actual transition must fit at/before
`knownUntilPs`, below UINT64_MAX. Count zero declares a known hold. After the
finite count, the last level remains held through the horizon; another period
is never inferred.

C lazily fills the same 512-edge queue from this descriptor. While producer edges
remain unmaterialized, another descriptor or nonempty raw batch returns `false`
for backpressure; an empty raw batch may still extend the horizon. Once no
producer edges remain, later input may follow the usual horizon/tail rules even
if materialized edges are still queued. `state().clki.periodicRemaining` counts
unmaterialized edges, separately from `queued` and `free`. Each externally
observable source edge is still serviced in native code: compact production
does not analytically skip the clock, peripheral or pin work.

`runUntilPs` returns the number of retired instructions. If the known-input
horizon is exhausted it returns normally at that earlier time; `state().clki`
reports `WAIT_INPUT`. It also exposes `horizonPs`, `level`, `queued`, `free`,
`periodicRemaining`, `status` (`COMPLETE`, `WAIT_CLOCK`, `WAIT_INPUT`), `aligned`
and BigInt `startupCK`.
Extend the horizon/edges and call again to continue. Bounded physical audio
capture preflights the entire requested sample interval; insufficient input
throws an explicit `CLKI WAIT_INPUT` before changing CPU/audio state.

A high/low hold preserves divider and pending CPU/IRQ phase. WDT, power/RESET
observation and NVM wall latency continue; source-CK startup and synchronous
peripherals advance only when their required real edges and gates permit it.
An unknown horizon is distinct from a declared stop. Silicon source-pad timing,
hardware phase and physical hot stop/restart behavior remain unmeasured; the
optional ideal validator does not replace that qualification. See the
[CLKI contract](../native/devices/attiny13a/clki-design.md) for event ordering,
divider and startup rules.

With CLKI selected, use bounded `runUntilPs`; unbounded `step`, `run`, `clock`,
`interrupt` and `runBlock` are rejected. Host EEPROM EERE/EEPE command writes
are rejected before execution; firmware can perform those operations with its
normal resumable stalls. EEPROM address/data and EEMPE setup remain available.
PB3 belongs to the CLKI stream, so separate digital/analog PB3 injection is
rejected. Explicit power and RESET receiver profiles remain available without
an RC table; programming still requires its explicit timing profile.

## CLI

```sh
node web-player/scripts/package-attiny13a.mjs pack firmware.hex firmware.attiny13a.json
node web-player/scripts/package-attiny13a.mjs pack firmware.bin firmware.attiny13a.json --eeprom eeprom.bin --configuration config.json
node web-player/scripts/package-attiny13a.mjs verify firmware.attiny13a.json
node web-player/scripts/package-attiny13a.mjs unpack firmware.attiny13a.json extracted-device
```

`pack` normally compiles Flash using the repository's bundled full-device
runtime, first checking the runtime's build hash. An existing pair can be
provided with `--translated firmware.wasm --runtime runtime.wasm`; this path
does not instantiate either module. `--no-flag-dce` applies only when compiling.
The generated package is verified again before writing. Output files and the
unpack destination directory must be new. `verify` and `unpack` load and verify
all bytes without running WASM; failed verification creates no extraction
directory. JSON status goes to stdout, errors to stderr with exit status 1.
Unpack emits Flash, EEPROM, both WASM binaries, configuration, manifest and a
small package metadata report.

Optional offline CPU optimization:

```sh
node web-player/scripts/package-attiny13a.mjs pack firmware.hex optimized.json --optimize Oz
```

Levels `O2`, `O3`, `Os` and `Oz` are supported. The tool uses the local pinned
SDK or `--wasm-opt /absolute/path/to/wasm-opt` / `MICROMUSIC_WASM_OPT`.
Stdout additionally records optimizer version/hash, flags and before/after hashes
and sizes. The existing package schema, runtime and loader remain unchanged;
the complete import set and embedded AVR manifest are preserved. Optimization
runs during packaging only. See [translator details](../native/AVR_TO_WASM.md).

Primary format references: [WASM binary module grammar](https://webassembly.github.io/spec/core/binary/modules.html)
and [WebCrypto digest / SHA-256](https://www.w3.org/TR/2017/REC-WebCryptoAPI-20170126/#SubtleCrypto-method-digest).
The device configuration follows the repository's documented ATtiny13A runtime
profile; the official device reference is
[Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
