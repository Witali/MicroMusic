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
stack-phase convention; the hardware phase audit remains part of stage3.

## 2 Remaining device behavior

- [ ] Handle phase-correct Timer0 PWM with variable TOP equal to zero.
- [ ] Model OSCCAL changes with an explicit oscillator calibration contract.
  Factory calibration reload and the reserved-bit mask are implemented; a
  measured CAL-to-frequency table and variable oscillator phase remain open.
- [x] Implement the BODCR timed sleep-disable sequence.
- [ ] Apply fuse-dependent oscillator startup and reset recovery delays.
- [ ] Resolve SPM command timing where the datasheet supplies a bound; expose
  explicit timing parameters where it does not.

Acceptance: supported register operations no longer fail merely because these
behaviors are missing; each behavior has focused tests and a documented time
and clock domain. Analog properties are parameters rather than invented facts.

BODCR includes the protected four-cycle write and three-cycle SLEEP windows,
fuse/mode gating and an explicit configurable recovery time. Its logical state
is observable separately from analog supply-threshold behavior.

## 3 Timing ambiguities and hardware validation

- [ ] Retain explicit choices for the conflicting first ADC sample timing and
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

- [ ] Package translated WASM, the peripheral runtime, Flash, EEPROM, fuses and
  timing configuration in a versioned artifact with integrity checks.
- [ ] Load and validate that artifact in the CLI and browser worker.
- [ ] Verify self-programming and cache invalidation after loading a package.
- [ ] Make the full ATtiny13A engine the default after integration and parity
  checks pass; retain explicit engine selection for comparisons.

Acceptance: a package reproduces the configured device without implicit host
defaults; CLI and browser execute the same firmware and physical output.

## 5 Performance without loss of timing accuracy

- [ ] Measure CPU translation/execution, peripheral scheduling, pin collection
  and audio filtering separately on identical firmware and sample intervals.
- [ ] Reduce repeated register-memory traffic and WASM helper calls where the
  event deadline proves a block safe; preserve live SREG bits at every exit.
- [ ] Cache translation using firmware, translator, runtime and configuration
  identities; invalidate changed Flash regions after self-programming.
  A bounded in-process module cache now uses the exact padded Flash image,
  compiler options, ABI and runtime module identity. Clocks/fuses stay in each
  runtime instance; changed Flash invalidates by image. Region-level
  retranslation and a persistent cache remain open.
- [ ] Evaluate moving audio filters into WASM using measured costs.

Acceptance: report reproducible cold and warm timings, output parity and cycle
counts. Keep optimizations only when those checks preserve device behavior.

## Execution and verification

Work in this order while developing independent peripheral fixes in parallel.
Commit each completed change separately and update this checklist with its
verification evidence. Run focused tests for each change and the full regression
suite at integration checkpoints. Never mark hardware checks complete from
simulation alone.

## Primary references

- [ATtiny13A Data Sheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
- [AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
- [WebAssembly Core binary instructions](https://webassembly.github.io/spec/core/binary/instructions.html)
- [Current instruction mapping and runtime contract](AVR_TO_WASM.md)
- [Device bus and scheduler contract](peripherals/device.md)
