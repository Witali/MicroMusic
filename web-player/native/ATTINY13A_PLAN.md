# ATtiny13A firmware transpilation plan

Complete the AVR binary to WebAssembly path for ATtiny13A, with peripheral
events synchronized to original CPU cycles and physical pin output collected
inside WASM. Other ATtiny and ATmega devices require separate profiles.

The virtual chip runs a supplied firmware image. External programming through
ISP/HVSP or a simulated programmer is outside the current scope and acceptance
criteria, as explicitly requested by the user. See
[`EMULATION_SCOPE.md`](EMULATION_SCOPE.md).

The current implementation lowers all 123 instruction-summary forms, connects
the device bus and peripheral scheduler, retranslates modified Flash, and
captures physical PWM output without JavaScript callbacks per instruction or
edge. These are the starting point, not a claim of complete silicon fidelity.

## 1 Instruction effects within CPU cycles

- [x] Audit the documented access timing of PUSH, POP, RCALL, ICALL, RET,
  RETI and interrupt entry; distinguish guaranteed timing from model choices.
- [x] Stage stack and register effects so an asynchronous reset cannot commit
  accesses belonging to later instruction cycles.
- [x] Audit other multicycle instructions, including pointer updates and LPM.
- [x] Test reset before, during and at instruction completion, normal execution,
  nested interrupts and physical output parity.

Acceptance: published cycle totals and access timing are preserved; a reset
aborts subsequent instruction effects at its exact scheduler timestamp.
Unspecified internal phases are documented as model choices.

Implemented in the full-device emitter and native IRQ bridge. Focused phase,
system, analog/NVM and physical-output tests exercise reset cancellation,
ordinary execution and output parity. See `AVR_TO_WASM.md` for the explicit
stack-phase convention; the hardware phase audit remains part of stage 3.

## 2 Remaining device behavior

- [ ] Handle phase-correct Timer0 PWM with variable TOP equal to zero.
- [x] Model OSCCAL changes with an explicit oscillator calibration contract.
  A caller-supplied128-entry CAL/frequency table selects a1ps physical timeline;
  missing CAL values fail explicitly. Integer phase survives CAL and CLKPR
  changes. The generated CPU and native PWM collector use relative deadlines
  while retaining integer absolute timestamps. A measured per-chip table and
  analog settling behavior remain hardware-validation work.
- [x] Implement the BODCR timed sleep-disable sequence.
- [x] Apply fuse-dependent oscillator startup and reset recovery delays.
  `fuseStartupProfile:1` enables source-clock and watchdog-pulse delays,
  external RESET release/reassertion and mode-dependent wake startup. The
  explicit zero-startup fixture remains available as profile 0.
- [x] Resolve SPM command timing where the datasheet supplies a bound; expose
  explicit timing parameters where it does not.
  Page erase/write use the documented 3.7–4.5 ms range; short commands require
  `spmCommandCycles`. No undocumented universal instruction duration is assumed.

Acceptance: supported register operations no longer fail merely because these
behaviors are missing; each behavior has focused tests and a documented time
and clock domain. Analog properties are parameters rather than invented facts.

BODCR includes the protected four-cycle write and three-cycle SLEEP windows,
fuse/mode gating and an explicit configurable recovery time. Its logical state
is observable separately from analog supply-threshold behavior.

## 3 Timing ambiguities and hardware validation

- [x] Retain explicit choices for the conflicting first ADC sample timing and
  ADIF behavior under SBI/CBI until measured on ATtiny13A hardware.
- [ ] Validate CLKPR transition timing and external RESET recognition/recovery.
- [ ] Create small firmware probes and an expected trace format for comparison
  with logic-analyzer or oscilloscope captures.
  Timer0 WGM5/TOP=0 now has source-only firmware, nine control/measurement
  profiles, trace framing/decoder tests and acquisition instructions in
  `peripherals/timer0-top-zero-probe.md`; silicon results remain pending.
- [ ] Record measured chip, clock, fuse configuration and measurement tolerance;
  update the default profile only when the evidence supports it.

Acceptance: each ambiguity has a reproducible probe and a documented outcome.
Hardware-dependent checks remain open until actual measurements are available.

## 4 Complete firmware delivery

- [x] Package translated WASM, the peripheral runtime, Flash, EEPROM, fuses and
  timing configuration in a versioned artifact with integrity checks.
- [x] Load and validate that artifact in the CLI and browser worker.
- [x] Verify self-programming and cache invalidation after loading a package.
- [ ] Make the full ATtiny13A engine the default after integration and parity
  checks pass; retain explicit engine selection for comparisons.

Acceptance: a package reproduces the configured device without implicit host
defaults; CLI and browser execute the same firmware and physical output.

Format v5 includes per-asset and envelope SHA-256, explicit clock/supply/RESET
configuration, optional CPU continuation/CLKI, embedded manifest and ABI validation.
Readers retain v1/v2/v3/v4
support, including retained original v1/v3 runtime regressions. A standalone
loader test runs with no default WASM files; Worker tests cover audio restart
and SPM.
The browser can open a local package and observes both PWM pins as stereo.
The default switch is additionally gated on real-time performance: browser
verification initially measured about 0.4x audio throughput on this host.

## 5 Performance without loss of timing accuracy

- [ ] Measure CPU translation/execution, peripheral scheduling, pin collection
  and audio filtering separately on identical firmware and sample intervals.
  The reproducible benchmark now separates cold/warm construction, coupled
  CPU/peripheral/pin capture and JS DSP. Exclusive CPU/peripheral timings still
  need instrumentation. All 13 firmwares passed 208 measured runs and 2496
  optimization-parity checkpoints; capture throughput was 0.29–0.95x real time.
- [ ] Reduce repeated register-memory traffic and WASM helper calls where the
  event deadline proves a block safe; preserve live SREG bits at every exit.
- [ ] Cache translation using firmware, translator, runtime and configuration
  identities; invalidate changed Flash regions after self-programming.
  A bounded in-process module cache now uses the exact padded Flash image,
  compiler options, ABI and runtime module identity. Clocks/fuses stay in each
  runtime instance; changed Flash invalidates by image. Region-level
  retranslation and a persistent cache remain open.
- [x] Evaluate moving audio filters into WASM using measured costs.
  JS DSP took 0.17–0.29 ms per 250 ms audio, compared with 262–872 ms capture.
  Keep the filters in JS while optimizing the coupled native execution path.

Acceptance: report reproducible cold and warm timings, output parity and cycle
counts. Keep optimizations only when those checks preserve device behavior.

Retained measurements and methodology:
[`reports/device-benchmark-20261023.md`](../reports/device-benchmark-20261023.md).
The report records individual trials, source/runtime identities and host
variation; its timings are not an isolated browser guarantee.

## Execution and verification

Prioritize these stages while developing independent peripheral fixes in parallel.
Continue independent software work when a hardware measurement is unavailable.
Commit each completed change separately and update this checklist with its
verification evidence. Run focused tests for each change and the full regression
suite at integration checkpoints. Never mark hardware checks complete from
simulation alone.

The sampling profile now attributes the largest repeated cost to native
`next_event` scans (about20% leaf samples on three representative firmwares).
Generated CPU bodies account for about14–15%; the JS bridge is below0.2%.
These are sampled function-body observations, not precise exclusive subsystem
timings. See [`reports/device-profile-20261023.md`](../reports/device-profile-20261023.md)
for source/runtime identities, naming methodology and limitations.

The scheduler now reuses deadlines only at an unchanged timestamp and state,
with explicit invalidation at every mutation boundary. The retained serial
[baseline/candidate measurement](peripherals/device-deadline-cache-benchmark.md)
compared 72 runs and 3384 endpoint snapshots with byte-identical PCM and full
CPU/peripheral state. Median paired gains were 1.14–1.19x with physical time and
1.12–1.24x with the compatible clock contract on this host. These are coupled
capture measurements with host variance; physical capture still misses real
time, so the default-engine performance gate remains open. That checkpoint's
runtime matched the measured candidate SHA-256. All 871 default regression tests passed
at this integration checkpoint. A new profile of the optimized runtime should
guide the next performance change. Measured OSCCAL curves and silicon probes
proceed when hardware is available.

## 6 Hardware coverage beyond firmware-visible registers

- [x] Connect the POR/BOD supply observer to the device scheduler, shared reset
  hold, reset-cause flags, VCC-dependent ADC/GPIO and nonvolatile operations.
  The observer, board integration, generated CPU bridge, physical capture and
  package path are connected and tested. Thresholds, hysteresis, durations and
  the Flash programming voltage boundary require an explicit profile. Below-
  voltage EEPROM/Flash operations retain uncertainty diagnostics across reset
  and every implicit NVM completion path.
- [x] Audit the external-clock, RESET electrical qualification and physical
  pin characteristics against explicit board profiles; distinguish logical
  injections from analog signal recognition.
  The [interface inventory](devices/attiny13a/interfaces.md) distinguishes the
  digital clock/RESET fixtures and optional qualification from unmeasured
  analog receiver and silicon phase behavior.
- [x] Implement external CLKI source events and stopped-clock behavior while
  preserving CPU instruction phases and independent peripheral time.
  The [board integration](devices/attiny13a/clki_board.md) connects exact source
  edges to PB3, CKDIV8/CLKPR, GPIO/ADC/Timer0 phases, startup and clocked wake.
  Bounded translated CPU/IRQ continuations retain latched operands and completed
  effects while the source holds high or low. WDT, power and NVM wall time
  continue independently. Package v5 validates the profile and continuation ABI.
  Arbitrary edges and finite high/low descriptors share the same native queue;
  descriptor refill, output draining and stereo integration stay in WASM.
  Optional ideal-signal qualification is explicit. Silicon clock phase and
  analog reception remain hardware-validation work, not completed measurements.
- [x] Add a separately profiled analog RESET receiver feeding the existing
  reset aggregator; keep prequalified digital inputs explicit.
  The device-owned receiver uses VCC-relative hysteresis and separate explicit
  qualification/propagation parameters. Physical deadlines feed generated CPU
  barriers, shared reset hold/startup and native audio. Package v4 preserves
  the profile; RSTDISBL gates the role and DWEN configurations are rejected.
  Atomic VCC/EXTRF updates prevent false reset release during source handoff.
  These are verified profile semantics; silicon calibration remains stage3.
- [x] Record the exclusion of ISP/HVSP and external-chip programming.
  A ready firmware image initializes the virtual device directly. No external
  programming backend or programmer transport is retained.
- [ ] Resolve documented debugWIRE pin/reset behavior and unsupported DWEN
  configurations. The audit found no authoritative wire protocol in the pinned
  manufacturer definitions; do not invent one.
- [x] Track applicable silicon errata and represent undefined outcomes explicitly
  instead of silently inventing deterministic success or memory corruption.
  DS80000857A identifies EEPROM writes below1.9V for revisions G/H/I, with no
  additional published clarifications. Both dynamic supply profiles and fixed
  configured VCC diagnose uncertain writes. Atomic/erase-only/write-only modes,
  unchanged reads and the exact1.9V boundary have focused regressions. Last-known
  bytes remain diagnostic data; no corruption or successful completion is invented.
- [x] Use the manufacturer's official device definition files as the address
  source for the model, generated register maps and new firmware tooling.
  Pinned Microchip ATtiny_DFP3.4.278 originals retain source URL, version,
  license and byte hashes. Generated C/JS/JSON/assembly views feed peripheral
  headers, CPU target placement and active stereo firmware. The repository
  rule is recorded in `AGENTS.md`.
- [x] Separate device geometry and register placement from the shared emitter.
  `lib/devices/attiny13a-profile.js` supplies the target parameters; registry
  lookup rejects unsupported devices and cache keys include the target name.
  Native hardware, emitted firmware WASM and runtime/package assets retain
  separate ownership. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

Acceptance: the coverage inventory identifies every supported interface and
its required profile. Standalone modules count as integrated only after the
generated CPU, scheduler and package path exercise them together.

Integration checkpoint, 2026-10-23: all 768 default regression tests passed,
plus 8 native-candidate preload/cache checks. Browser verification opened a
CLI-built stereo package, checked its fuses, started physical pin playback and
observed zero lost IRQs. The Timer0 probe decoder's four synthetic checks and
nine successful assembly profiles validate the probe tooling; no hardware
trace has been supplied.

Later integration checkpoint, 2026-10-23: all852 default regression tests passed
after the calibrated-clock, power-profile, official-register and analog-input
deadline changes. Device-profile separation additionally passed37 focused
checks, including three new profile checks, standalone package loading and the
original v1 runtime fixture. All13 retained firmware translations remained
byte-identical after extracting target geometry, and active stereo firmware
remained byte-identical after adopting official assembly symbols. Hardware
measurements and performance gating remain open.

Analog RESET integration checkpoint, 2026-10-23: all 919 default regression
tests passed with the receiver, atomic supply/source handoff and package v4.
Coverage includes 22 receiver checks, generated instruction cancellation,
audio integration, watchdog-preserved qualification, RSTDISBL/digital bypass,
original v1/v3 packages, invalid profiles and missing/wrong-signature RESET
exports. The runtime has no host imports, fixed two-page memory and 82 exports.
External CLKI/CPU continuation is still unimplemented; its audited contract is
retained separately. No physical programming interface has been added.

Fixed-supply EEPROM erratum checkpoint: six below1.9V mode/supply cases
reproduced the missing diagnostic before the fix. All 13 new fixed-VCC cases
then passed, including exact1.9V/5V completion and a low-voltage read. The
post-fix focused NVM, power, RESET, cache and package regression set passed
111/111. This later native change retains the same import-free, fixed-memory
runtime contract; the 919-test result above belongs to the RESET checkpoint.

CPU continuation checkpoint, 2026-10-23: the first integration passed all979
default regression tests, including all123 official instruction forms sliced
at half edges and adjacent1ps deadlines. A subsequent native review found and
fixed zero-clock SLEEP retirement during immediate INT0/BOD wake recovery.
The final focused set passed66/66 with that fix, native IRQ/reset tests,
22 actual generated WAIT/resume oracles, package loading and native audio.
All13 retained default firmware translations are byte-identical to39e4ecb.
The rebuilt native runtime is100230bytes,88exports, no host imports and fixed
two-page memory. Its hash is878bd0266347ad9544f07cf2825f7720ddc95f641304ccda3646ad6a58730655.
The optional continuation path uses the existing internal physical source;
PB3 CLKI/divider/startup integration, electrical profiles and a versioned
package ABI remain open. ISP/HVSP/programmer support remains excluded.

External CLK integration checkpoint, 2026-10-23: all1128 default regression
tests passed, including20 new finite-source/device/audio acceptance checks.
All123 instruction forms also execute from unequal external phases with exact
half-phase/1ps observations. The source, PB3, divider, GPIO/ADC/Timer0 sampling,
reset/startup/wake, native IRQ entry and package v5 now exercise one integrated
clock model. WDT and NVM continue during a held source; known holds and unknown
input horizons remain distinct.

A single descriptor supplied80000 source transitions at20MHz for native stereo
capture without JavaScript source refills. New regressions first reproduced
output-ring overflow during Power-down, fuse startup and all three LPM forms
at CLKPR/256. Native buffered waits and clock phases now drain internally,
preserve exactly-once effects and match the internal physical-clock reference.
The output stream, phase policy, remaining physical limitations and acceptance
coverage are described in [clki_board.md](devices/attiny13a/clki_board.md).

The rebuilt runtime is112340bytes,103exports, no host imports and fixed two-page
memory. Its SHA-256 is
`ae66ad2e64f8e96af046cd02b04f49c82c371026b8686bd54647678c8a8efa97`.
This checkpoint closes21 of30 checklist items. The remaining nine include
hardware measurements, Timer0 TOP=0, debugWIRE behavior, performance/cache work
and the default-engine gate. The earlier open-CLKI statements above describe
historical checkpoints. ISP/HVSP and external programming remain excluded.

## Primary references

- [ATtiny13A Data Sheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
- [AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
- [WebAssembly Core binary instructions](https://webassembly.github.io/spec/core/binary/instructions.html)
- [Microchip ATtiny DFP3.4.278](https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack)
- [Imported manufacturer definitions and provenance](../vendor/microchip/ATtiny_DFP/3.4.278/README.md)
- [Current instruction mapping and runtime contract](AVR_TO_WASM.md)
- [Device bus and scheduler contract](peripherals/device.md)
