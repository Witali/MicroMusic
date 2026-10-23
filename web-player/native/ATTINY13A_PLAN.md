# ATtiny13A firmware transpilation plan

Complete the AVR binary to WebAssembly path for ATtiny13A, with peripheral
events synchronized to original CPU cycles and physical pin output collected
inside WASM. Other ATtiny and ATmega devices require separate profiles.

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
- [ ] Model OSCCAL changes with an explicit oscillator calibration contract.
  Factory calibration reload and the reserved-bit mask are implemented; a
  measured CAL-to-frequency table and variable oscillator phase remain open.
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

Format v1 includes per-asset and envelope SHA-256, explicit configuration,
embedded manifest and ABI validation. A standalone loader test runs with no
default WASM files; Worker tests cover initialization/audio restart and SPM.
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

The next software priority is to instrument the coupled CPU/peripheral path and
reduce scheduler work between known events. Keep instruction-effect barriers
and physical output parity as the acceptance conditions. A measured OSCCAL
frequency curve and silicon probes proceed when hardware is available.

Integration checkpoint, 2026-10-23: all 768 default regression tests passed,
plus 8 native-candidate preload/cache checks. Browser verification opened a
CLI-built stereo package, checked its fuses, started physical pin playback and
observed zero lost IRQs. The Timer0 probe decoder's four synthetic checks and
nine successful assembly profiles validate the probe tooling; no hardware
trace has been supplied.

## Primary references

- [ATtiny13A Data Sheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
- [AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
- [WebAssembly Core binary instructions](https://webassembly.github.io/spec/core/binary/instructions.html)
- [Current instruction mapping and runtime contract](AVR_TO_WASM.md)
- [Device bus and scheduler contract](peripherals/device.md)
