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

Post-CLK measurement, 2026-10-23: the
[current emulator speed report](../reports/emulator-speed-20261023.md) retains
195 timed runs and576 firmware checkpoints against the112340-byte runtime.
The arithmetic kernel delivers7.16million instructions/s with the compatible
full-device clock and3.89million with physical continuation. Full20MHz CLKI
capture needs410ms for25ms at D1, and293ms at D256 despite the much smaller
CPU workload. Three real firmware excerpts run at0.62–0.91times real time in
the compatible full-device mode. Source-edge/scheduler work is the next
profiling target; exclusive subsystem timings and the default-engine gate
remain open. These measurements preserve the implemented phase semantics.

Post-CLK tracing checkpoint: the
[current runtime profile/call trace](../reports/runtime-profile-20261023.md)
retains40 profiles/12566 attributed samples and five source-entry counter traces.
Real firmware spends10–13% of leaf samples in `next_event`,10–13% in integer
time conversion and roughly15% in generated CPU bodies/drivers. At20MHz CLKI,
25ms produces6000000 analog-input updates and13–14million ADC-advance entries;
analog function bodies account for25–35% of sampled leaves. All diagnostic
cases match production PCM and complete public/memory observations. Prioritize
changed-pin propagation, same-time analog coalescing, deadline conversion and
dirty-register publication. These are measured candidates; no speedup or exact
exclusive subsystem time is claimed from sampling alone.

### Peripheral activity and lazy state advancement

Saved improvement plan, 2026-10-23. This refines stage5; it is planned work,
not an implemented scheduler optimization or an additional completed item.
The changed-voltage/trigger-flag optimization is already implemented separately.

Goal: avoid regular calls to inactive peripheral modules while retaining exact
register values, interrupt flags, wakeups, pin transitions and clock phases.
External connections and observers are additional consumers, not the sole
criterion for whether a peripheral is needed by firmware or another module.

| Module | Activity and retained dependencies |
|---|---|
| ADC | Conversions, auto-trigger dependencies and configuration changes. Preserve the enabled prescaler's phase even between conversions. |
| Comparator | Selected input/reference changes, bandgap startup, propagation and synchronization while enabled. Account for ADC multiplexer routing even when ADC conversions are disabled. |
| Timer0 | Counting, compare/overflow flags, PWM and synchronized external T0 input. A stopped counter does not necessarily stop the free-running prescaler; retain its phase analytically. |
| GPIO | Pin/DDR/PORT/pull-up changes and pending synchronization. Keep PINB reads, internal consumers, INT0/PCINT flags, sleep wakeup and alternate functions correct for externally unconnected pins too. |
| Watchdog | Enabled reset/interrupt operation, fuse-forced enable and protected control windows. Preserve its independent time domain and reset behavior. |
| EEPROM/Flash | Pending read/program stalls, completion events and protected command windows. Keep ready IRQ levels and Flash generation/invalidation correct even when no periodic processing is needed. |

Implementation order:

1. Audit each module's activation, internal dependencies and side effects using
   the official ATtiny13A data sheet and pinned manufacturer definitions. List
   mutations that can create a new event or make a previously idle module live.
2. Maintain native activity masks or an active-module list and each module's
   last-serviced time/phase. Recompute activity at relevant register writes,
   reset, PRR/sleep/clock-domain transitions, input changes and connection or
   observer changes. Invalidate cached board deadlines whenever required.
3. Remove inactive modules from recurring service and deadline scans. Retain
   asynchronous deadlines independently of CPU clocks. At the exact bus/input
   timestamp, settle preceding events before reads, mutations or reactivation;
   account for skipped time analytically without replaying every elapsed tick
   or treating a clock-gated interval as running time.
4. Advance GPIO synchronization only while its pipeline has pending work. After
   it settles, reconstruct the correct clock phase before a later mutation and
   resume on the actual required edge. Preserve same-timestamp ordering: new
   zero-delay events must not be skipped merely because time was serviced once.
5. Separate internal pin state from external observation. Consider explicit
   per-pin trace/audio subscriptions so unobserved output history need not be
   buffered. Preserve the existing full-trace contract by default; CPU and
   peripheral dependencies remain active regardless of external subscriptions.
   Retain every required CLKI transition, divider residue and bounded-input
   horizon. Keep all hot-path dispatch and output buffering inside WASM.
6. Implement and measure changes incrementally. Add focused boundary/parity
   tests, run the full regression suite, then compare serial alternating old/new
   runs on identical firmware/input/sample intervals. Retain individual paired
   timings and variance; activity checks must justify their own hot-path cost.

Acceptance: exact parity of CPU cycles/phases, registers and interrupt flags,
SRAM/EEPROM/Flash, wake/reset behavior, subscribed pin timestamps and PCM.
Exercise mid-instruction activation, same-time inputs and writes, disabled IRQs
with live flags, ADC/comparator routing, stopped Timer0 prescaler phase,
PRR/sleep/resume, protected windows, pending NVM work and internal/CLKI clocks.
Reattachment or newly enabled observation must not invent historical trace data.
Use source-entry counters to confirm work was removed and uninstrumented paired
benchmarks to establish speed; small results within host variation stay
inconclusive. No per-edge JavaScript callbacks, cross-device code mixing or
external programmer support are introduced by this plan.

The next analog step has a separate audited
[ADC activity contract](devices/attiny13a/analog-activity.md): omit recurring
ADC advancement/deadline queries only with ADEN clear, preserving every
timestamped component API, trigger/IRQ level and comparator operation. The
comparator remains the shared monotonic-time anchor. Broader analog gating
requires its own phase/dependency proof; this contract is not completion evidence.

ADC experiment checkpoint, 2026-10-24: both recurring-call guards and separate
enabled/disabled loops preserve model behavior but fail the speed gate. The
initial candidate passed1216/1216 tests; the split version passed108 focused
checks. Together480 timed runs retain1376 exact pairwise checkpoints. Despite
millions fewer ADC entries, the initial active-ADC internal-clock control is
slower in8/8 pairs (0.942x median), and split rhythmic physical capture is
slower in8/8 pairs (0.915x). Other times show substantial host variation. Both
candidates were restored out of production. The
[complete report](../reports/adc-activity-20261024.md) retains sources, test
adaptations, exact harness, timings and counters. Activity gating for ADC and
the other unoptimized modules remains open. Do not equate removed entries with
speed; include enabled-module controls and improve cost attribution/isolation
before more fine-grained per-call guards.

### AVR to WASM generation and execution improvements

Saved improvement plan, 2026-10-23; next-step details updated 2026-10-24.
This also refines stage5; implemented work is recorded in the checkpoint below,
and the remaining priorities stay open. Treat warmed execution speed separately
from translation, WASM compilation,
module size and retranslation after SPM; improvements in one do not establish
improvements in the others.

Starting point at the saved2026-10-23 checkpoint:
[`avr-transpiler.js`](../lib/avr-transpiler.js) generated ordinary
optimized blocks only when `!resumable`. The exact resumable path dispatched
individual instruction functions. AVR registers remain in shared linear memory;
flag elimination currently applies within ordinary blocks. The phase emitter
saves nine i32 temporaries and one f64 temporary on a suspended phase, rather
than saving only values live across that particular boundary. These are concrete
candidates, not measurements of their individual cost.

Implementation priorities:

1. Add a guarded block path for resumable execution. Execute several generated
   instructions between proven CPU observation/interruption boundaries, retaining
   the existing single-instruction phase path when the proof fails or a deadline
   is near. Include pending IRQs, SEI/RETI delay, asynchronous reset, known input
   horizons, instruction-count limits and host/debug observation deadlines.
   Native peripherals must still process every required CLK edge and event;
   batching CPU work must not silently batch away the external waveform.
2. Keep AVR register values in WASM locals within accepted blocks. Load values
   when needed and publish dirty registers at every observable exit, before
   relevant helpers, ISR entry or suspension. Guard dynamic LD/ST aliases to
   registers and I/O; direct register-file memory access must see coherent state.
   Cancel effects from later instructions if reset interrupts execution.
3. Extend flag liveness across eligible connected blocks and evaluate deferred
   flag materialization. Preserve each instruction's actual flag dependencies,
   including carry and chained Z. SREG reads, ISR entry, debugger/host observation
   and fallback exits must materialize the exact required state. Global interrupt
   masking alone does not prove that flags are dead. Retain differential checks
   against the full-flags path.
4. Add constant propagation, dead-store elimination and small sequence rewrites,
   including register-pair operations, inside proven safe spans. Preserve all
   original AVR cycles, PC/error reporting, intermediate observation boundaries
   and I/O side effects even if fewer WASM operations represent the sequence.
5. Lower eligible control-flow regions and loops to direct WASM control flow,
   reducing repeated instruction-table `call_indirect` dispatch. Keep a guarded
   table/fallback path for indirect targets and entries outside the region.
   AVR call/return stack bytes remain firmware-visible SRAM state; native WASM
   calls alone cannot replace those semantics.
6. Compute temporary-value liveness across instruction phases. Save/restore only
   values needed after a particular suspension, and evaluate a shorter path for
   instructions that complete within the available budget. Resume without
   replaying bus reads/writes, stack operations or protected commands; keep the
   full context path as an oracle until parity is established.

For loading and retranslation, separately evaluate reachable-code generation
from reset/interrupt vectors and known branch targets, with safe handling of
dynamic jumps and code/data ambiguity. Do not assume unvisited Flash words can
never be executed. Evaluate compilation in regions and replacement after SPM;
invalidate every affected block and dependency, including cross-region blocks
and any folded Flash reads. Persistent cache keys must cover firmware, compiler
version/options, device profile and exact runtime ABI/identity. Keep per-device
mutable state outside cached compiled modules.

Validation: use the official AVR instruction descriptions and WASM specification
linked below. Start with guarded resumable blocks and register locals, measuring
each change separately. Compare against the existing generated instruction path
at cycle/half-phase, bus and observation boundaries, including all123 instruction
forms, flags, pointer aliases, skip/branch timing, nested IRQs, reset during an
instruction, sleep, CLKPR/OSCCAL, unequal/held CLKI phases and SPM invalidation.
Require exact registers/SREG/SRAM/EEPROM/Flash, retired counts, pin timestamps
and PCM, plus package and debugger compatibility. Run focused tests and the full
suite at integration checkpoints; retain serial paired uninstrumented timings
and compilation/size data. The older sampled CPU share is not a prediction of
the speedup available in the current runtime. Preserve the device/translator/
generated-code separation and add no per-instruction JavaScript callbacks.

#### Register-local experiment contract

Use `ad66d6d` as the measured baseline for this compiler-only experiment, with
the identical native runtime in both variants. Begin with register-only blocks
already accepted by the resumable deadline guards; keep memory/I/O and rejected
blocks on the existing instruction path. Do not combine this measurement with
new peripheral activity changes.

- Give each accepted block a fresh register map. Load an incoming register only
  when first needed, retain updated values in locals and flush dirty registers
  before retirement, native helpers or another observable exit. Reload on the
  next block entry; host mutations and fallback instructions must remain visible.
- Preserve byte semantics on every cached write, including the low byte of
  ADIW/SBIW. ASR must sign-extend the current cached byte. Allocate register locals
  separately from ALU temporaries and account for parameter-index remapping.
- Keep the existing clock-before-effects contract and event guards. A reset or
  fault that prevents the span from completing must not publish speculative
  register values. Expanding to memory instructions requires explicit alias and
  bus-phase proofs before enabling that path.
- Add differential cases for signed shifts after writes, register-pair carry,
  dependent flags with optimization enabled/disabled, all 32 registers, repeated
  block entry and transitions through memory/I/O fallback and IRQ boundaries.
- Prove both block execution through public runners and the register cache's
  emitted structure. Decode WASM instructions and their immediates: repeated
  INC of one register should need one incoming load and one dirty flush; an
  initial LDI should eliminate that incoming load. Raw opcode-byte counts and
  state parity alone do not prove that the optimization ran.
- Run focused and full regression checks, then quiet serial paired measurements
  on real firmware and arithmetic kernels. Record individual timings, output
  parity, translation/compilation time and module size. Synthetic gains do not
  establish real-firmware gains; retain the change only with measured benefit.

Result, 2026-10-24: candidate `6e04e5b` passed1207/1207 tests, including20 new
structural/differential cache checks, and208 serial timed runs with656 exact
pairwise state/PCM checkpoints. It did not establish an execution-speed benefit:
three physical firmware medians were1.011x/0.996x/0.997x and the long arithmetic
loop1.000x, with firmware module sizes increasing. Commit `b610be3` restored the
previous emitter; register locals are not enabled in production. The complete
[experiment report](../reports/register-locals-20261024.md) retains the candidate,
exact harness, raw timings, variance and validation. Do not repeat this isolated
change or claim speed from reduced load/store counts alone.

Revisit register locals alongside larger control-flow regions or other proven
transformations. Cross-block flag liveness, constant/sequence optimization,
direct control flow and smaller continuation contexts remain open compiler
candidates. Evaluate reachable-code generation, region recompilation and
persistent caching separately, with SPM invalidation and complete cache
identities. The independent ADC activity experiment above also failed its
speed gate. The next performance step must resolve these measured guard costs
and timing uncertainty before retaining more fine-grained dispatch changes;
the exact scheduling/dependency contracts remain requirements.

Implementation checkpoint, 2026-10-24: register-only resumable blocks now use
the existing phase context and native clock bridge. Strict event/observation
guards, IRQ delay/pending checks, exact retirement capacity and physical-time
capacity retain the original generated instruction path whenever a whole block
cannot fit. External CLKI still processes every source phase individually;
memory/I/O instructions retain their existing bus phases. The arithmetic still
accesses registers in shared memory, so register locals and the remaining
compiler priorities are open. The counter/half-phase boundary regressions and
all123 instruction forms pass; the complete integration suite passed1187/1187.
Native WASM probes also require actual14-cycle block calls from run/runUntil;
state parity alone had missed an inverted dispatch comparison. A shared
conservative event budget now protects both CPU modes from rounded physical
RESET ties, including the9MHz222223ps boundary and its adjacent picoseconds.

The first peripheral-activity change also skips recurring idle EEPROM/Flash
service and deadline queries, using the authoritative controller state. NVM
reads/writes/commands catch up at their exact timestamps, and the ready IRQ
remains a separate live level. Its24 differential checks cover internal and
held/unequal external clocks, protected windows, programming stalls, reset,
sleep/PRR and supply ties. Activity gating for the other modules remains open.
See the [NVM activity contract](devices/attiny13a/nvm-activity.md) and
[CPU block contract](devices/attiny13a/cpu_phase.md).

The rebuilt112668-byte runtime retains103 function exports plus exported memory
(104 exports total), no imports and fixed two-page memory, SHA-256
`9a3461976f84d456ca6f2a1c8b2a24f0b1dadbc85ced2c45d20f1eeffbbc2bde`.
The [three-way optimization report](../reports/planned-optimizations-20261024.md)
retains234 final timed runs and1476 pairwise checkpoints. Three physical-time
firmware examples have median paired total gains of1.365–1.640x, positive in
all18 pairs. The short/long arithmetic loops show2.610x/22.123x; their synthetic
gains are separate from real firmware. All chip state and PCM match, with only
the intentionally earlier private scheduling hint validated separately against
the old runtime. Native-only versus candidate diagnostics remain fully equal.
Ordinary generated code stays byte-identical for all13 retained firmwares in
both ABIs. Initial/preactivation timings, exact harness sources, individual
variance and native entry counters are retained too. CLKI still services every
source phase. This improves execution without closing real-time acceptance.
This is partial stage5 progress; the checklist remains21 of30 complete with
nine open, including silicon measurements and the default-engine gate.

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

Analog propagation optimization checkpoint, 2026-10-23: changed-only PB voltage
and ADC trigger-flag notifications preserve all input/event phases and pass
1139/1139 tests. Against `a2bd135`, eight paired trials show median1.300x/1.447x
speedup for the20MHz CLKI /1,/256 kernels; ordinary firmware gains remain small
relative to host variation. The112522-byte import-free runtime is recorded with
exact state/PCM/pin parity and source-entry reductions in
[the optimization report](../reports/analog-propagation-20261023.md).
This does not close the exclusive-timing or default-engine acceptance items;
the checklist remains21 of30 complete, with nine open. External programming
remains excluded.

## Primary references

- [ATtiny13A Data Sheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
- [AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
- [WebAssembly Core binary instructions](https://webassembly.github.io/spec/core/binary/instructions.html)
- [Microchip ATtiny DFP3.4.278](https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack)
- [Imported manufacturer definitions and provenance](../vendor/microchip/ATtiny_DFP/3.4.278/README.md)
- [Current instruction mapping and runtime contract](AVR_TO_WASM.md)
- [Device bus and scheduler contract](peripherals/device.md)
