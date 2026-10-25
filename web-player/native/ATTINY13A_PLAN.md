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

Integration checkpoint, 2026-10-24: merged main's common ATtiny13A/ATtiny88
music core with the generated and physical ATtiny13A paths. All native paths
share the profile-aware state wrapper; physical board defaults stay in the
ATtiny13A adapter, using pinned Microchip definitions. Historical package
layouts and direct native phase fixtures remain covered. The main stereo
image is byte-identical after symbolic register regeneration. All 1632 Node
checks pass, including device switching and the two additional tool suites;
the assembler's two focused Python checks also pass. See the
[integration record](../reports/main-transpiler-integration-20261024.json).
ATtiny88 transpilation/full peripherals and performance/hardware acceptance
remain separate work; this merge does not close another item in the 21/30 plan.

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
  The unsupported pulse boundary is explicit, including active TOP=0 with
  pending OCR0A>0. Stopped/gated clocks and an edge-free external T0 hold remain
  usable; no first-pulse buffer transfer is assumed. Non-PWM preload establishes
  a known nonzero TOP before selecting WGM5. This fixes the diagnostic boundary,
  not the missing silicon counter/IRQ behavior.
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
  Timer0 WGM5/TOP=0 now has source-only firmware, twelve control/measurement
  profiles, trace framing/decoder tests and acquisition instructions in
  `peripherals/timer0-top-zero-probe.md`. The corrected PB2/T0 and PB4 trace-clock
  mapping matches the manufacturer ATDF; all12 profiles assemble and the four
  nonzero controls execute through the generated CPU/native board/decoder.
  [CLKPR](peripherals/clkpr-probe.md), [RESET](peripherals/reset-probe.md) and
  [ADC](peripherals/adc-probe.md) now add25 source-only profiles and shared wire-v2
  framing/decoding. All25 execute actual images under continuous external CLKI
  in explicit software fixtures; the ADC probe distinguishes both configured
  first-sample choices in80 synthetic conversions. The
  [CPU phase probe](peripherals/cpu-phase-probe.md) adds22 actual firmware
  profiles,114 queued RESET cuts and raw SRAM/GPR snapshots before reboot
  initialization. NOP qualifies hardware retention separately; RET/RETI's
  individual read latches remain unobserved. These are tooling/model checks,
  not silicon evidence or complete internal phase coverage. See the
  [peripheral acquisition report](../reports/hardware-probes-20261024.md) and
  [CPU acquisition report](../reports/cpu-phase-probe-20261024.md). Hardware
  captures, internal read-phase oracles and measured uncertainty remain open.
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

Pin-observation checkpoint, 2026-10-24: host trace and native PCM now have
independent1024-record queues. Host draining cannot steal audio transitions;
explicit per-pin subscriptions suppress history without disabling live GPIO or
internal consumers. Resumable PCM collection occurs at sample boundaries and
total queue pressure; ordinary clocks/waits retain eager collection to avoid
per-instruction guard costs. Long phases restore entry headroom before their original advance;
eager-first400-NOP/700-cycle-SPM regressions cover ordinary and resumable paths
and wrapped heads. All1276 Node tests pass, including68 new queue/observer/
pressure checks. The22 CPU acquisition profiles/114 RESET cuts and25 existing
CLKPR/RESET/ADC profiles also pass on the rebuilt runtime. No silicon data was
added. The [report](../reports/pin-observation-20261024.md) retains the defect,
independent eager oracle, source-entry counts, paired timing experiment and
earlier checkpoints. Renderers preserve explicit/default observers; automatic
host-history opt-out was not retained because its separate benefit was
inconsistent. Broader peripheral gating, exclusive cost attribution and the
default-engine performance gate remain open; the main count stays21/30.
The final416-run/2604-checkpoint comparison has physical-audio median paired
gains1.145–1.165x versus the original runtime (23/24 positive pairs), with
substantial host variation. Direct compatible/physical control medians are
0.960x/0.928x and need separate cost/layout attribution. Do not claim a general
CPU gain or close the default-engine gate; real-time throughput still falls short.

Long internal-phase correctness checkpoint, 2026-10-24: restoring entry
headroom alone did not prevent overflow within one long native advance.
Buffered internal-source requests longer than128 half periods now yield at
512 records after settling the current timestamp; the existing native bridge
drains and resumes the remaining phase. An independent host-trace integral
reproduces six old-runtime overflows and matches exact PCM/complete hardware
observations after the fix at9/9.6/20MHz. Fourteen native cases cover pressure/
wall/completion/reset ties, fractional phases, wrap, CLKPR, ordinary-fault
endpoints and zero trailing commits during BOD recovery. All1302 default tests
pass. The ordinary/short event loop is unchanged. The
[report](../reports/internal-audio-spans-20261024.md) retains reproduction,
test evidence and separate serial performance controls. This closes a boundary
gap within stage5; the main count remains21/30, with nine open and no new
physical-chip measurements.

Its312-run/1932-checkpoint serial performance control finds a cost rather than
a general gain: rhythmic compatible execution is slower in8/8 pairs (0.946x),
and CLKI /1,/256 in7/8 each (0.894x/0.880x), with substantial variation in other
cases. Forcing the rare helper to be noinline produces byte-identical WASM;
the probe is archived and not retained in source. Keep the correctness repair,
then distinguish ordinary continuation cost from module/code-layout and host
variation with identical-runtime controls and fresh profiles. This is the next
stage5 attribution task; do not count the repair as a speed optimization or
close the real-time/default-engine gate.

Balanced-control checkpoint, 2026-10-24: four labels with identical-runtime
pairs, equal full-workload warmups and balanced positions/adjacent pairs now
separate host variation from cross-version changes. The initial CLKI /1 case
already used the correct divisor; the strengthened runner asserts actual
divisors explicitly. Exact rebuilt optimized-function inventories establish
that the added buffered caller changed `service` outlining, while preserving
the distinction between raw relocations and changed normalized bodies.
An isolated `always_inline` wrapper experiment passed125 focused checks and
6636 exact checkpoints across832 timed executions plus208 warmups, but failed
the performance gate. Its apparent gains overlap material identical-binary
variation, and both CLKI cases favor it in only3/16 trials. Production was
restored exactly to `c302a77`; the1302-test correctness result still refers to
that exact core. The [report](../reports/runtime-controls-20261024.md) retains
sources, exact rejected binary, maps, raw observations and isolated reproduction.
All three control experiments total1056 timed executions,320 warmups and8140
checkpoints. Earlier slowdown ratios are observations from their recorded run,
not a stable regression or proved source-level attribution. Stage5 remains
open; the main count stays21/30. Next work needs a fresh profile and the same
identity controls before another scheduling or compiler optimization is kept.

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
linked below. Guarded resumable blocks are implemented; choose further changes
from a fresh profile and measure each separately. The rejected isolated register-
local experiment below must not be repeated without a new amortization strategy.
Compare against the existing generated instruction path
at cycle/half-phase, bus and observation boundaries, including all123 instruction
forms, flags, pointer aliases, skip/branch timing, nested IRQs, reset during an
instruction, sleep, CLKPR/OSCCAL, unequal/held CLKI phases and SPM invalidation.
Require exact registers/SREG/SRAM/EEPROM/Flash, retired counts, pin timestamps
and PCM, plus package and debugger compatibility. Run focused tests and the full
suite at integration checkpoints; retain serial paired uninstrumented timings
and compilation/size data. The older sampled CPU share is not a prediction of
the speedup available in the current runtime. Preserve the device/translator/
generated-code separation and add no per-instruction JavaScript callbacks.

#### Next experiment queue

Saved follow-up priorities, 2026-10-24. These are separate experiments, not a
promise of speedup or additional completed checklist items.

Post-merge sampling checkpoint: [24 current-runtime profiles](../reports/post-main-profile-20261024.md)
retain exact production PCM/state parity across six real-firmware and two direct
kernel cases (20,231 work-stack samples). The real-firmware hotspots include
`next_event`, `ratio` and `duration`; try reducing repeated event/time conversion
as the next isolated native experiment, preserving integer residues and event
boundaries. Kernel sample counts are small. Sampling is not exclusive timing or
a speedup claim; balanced uninstrumented controls, CLKI and enabled-ADC cases
remain mandatory before acceptance. Continuation liveness stays separate.

Equal-rate arithmetic checkpoint: the [identity fast path](../reports/clock-identity-20261024.md)
passes 1633 tests but fails the real-firmware speed gate. Six completed cases
retain 384 timed runs, 96 warmups and 5688 exact checkpoints; physical medians
are 0.967x/0.960x/0.980x. The remaining performance cases were stopped, with the
incomplete marker preserved. Production was restored exactly. Keep the added
full-width arithmetic boundary coverage and do not repeat this condition-only
guard. Next, test avoiding the overflow-check division when both multiplicands
fit 32 bits, with a separate addition-overflow check for a 64-bit carry and the
unchanged wide fallback. This is a hypothesis, not a retained optimization;
acceptance still needs CLKI/active-ADC and balanced identity controls.

Bounded-multiplier checkpoint: that [32-bit product candidate](../reports/clock-multiply-20261024.md)
passes all 1634 checks but regresses in both screening cases (0.945x/0.947x,
64 timed runs, 32 warmups, 1128 exact checkpoints). Production is restored;
the remaining timing matrix was not run. Keep the independent boundary tests.
Next inspect automatic Binaryen optimization of generated CPU modules, separately
from the C runtime already built with optimization. Check ABI/dispatch geometry,
embedded manifest, traps, exact state/PCM/pins and half-phase observations before
measuring warmed execution and cold optimization/compilation costs separately.

Automatic generated-WASM checkpoint: [Binaryen133 O3/Oz](../reports/generated-wasm-opt-20261025.md)
passes1641/1641 tests, including all123 forms at actual CLKI half phases and
adjacent1ps stops, public package/CLI paths and SPM invalidation during a hold.
Oz preserves exact PCM/state/pins in all13 workloads (26 parity runs,
168 checkpoints) and reduces physical firmware CPU modules by69–70%.
The four-row timing screen retains128 timed runs,64 warmups and2304 checkpoints;
physical speed gains are unproven. Retain explicit offline `--optimize` only,
with full bridge imports and manifest preserved. Default generation and native
runtime stay unchanged. Compilation observations are validation-warmed, not
cold-start measurements. Next implement per-phase temporary liveness against
the full-context oracle; automatic size optimization does not remove that work.
The checklist remains21/30, with nine open items.

Phase-local checkpoint: [generation-time temporary liveness](../reports/phase-locals-20261025.md)
is implemented as explicit `optimizePhaseLocals:true`, with the full-context
default retained. All1649 tests pass; all123 forms/four C/Z combinations match
at internal/external half phases and1ps observations. Thirteen workloads retain
exact PCM/state/pins and byte-identical default translations against `c8cf6bd`.
Physical firmware CPU modules shrink23.8–23.9%; native80-byte context allocation
and hardware timing are unchanged. Two controlled timing screens retain192
timed runs,96 warmups and3456 checkpoints. Even the shared-CPU-Module/GC-outside
screen remains too variable to prove a speedup, so default activation and the
full performance gate stay open. Next compiler experiment: cross-block SREG
liveness with every externally observable exit preserved. This closes no new
hardware checklist item; the count remains21/30.

Inter-block SREG checkpoint: [guarded two-block fusion](../reports/flag-regions-20261025.md)
passes1662 candidate checks and the13-case parity matrix. Untimed million-
instruction traces prove1/1789/15614 accepted regions on rhythmic/Lumiere/HQ4,
with11698 exact state/pin checkpoints and active IRQs. The two-case timing screen
does not show a speed gain (0.993x/0.958x with noisy identity controls), while
modules grow1.2–1.6%. The prototype is rejected and archived, not retained as
an option. Compiler/runtime sources are restored exactly to `ae265f7`; three
new SREG-observability regressions remain and all1652 restored tests pass.
The historical-generator loader additionally handles its phase-local dependency.
Next compiler experiment: constant/short-sequence folding within the existing
guards, preserving original cycles and all observable register/SREG exits.
Default activation, hardware evidence and the full performance gate remain open.

Constant-fold checkpoint: [the straight-line symbolic pass](../reports/block-constants-20261025.md)
passes1660 tests and all13 PCM/state/pin workloads, including fixed-width numeric
oracles and200 mixed expression trees against actual WASM. Whole physical modules
shrink only0.19–0.29%; after Binaryen Oz, additional savings are52–471 bytes.
The64-run timing screen gives1.022x/1.011x with identity variation larger than
those gains. The dedicated pass/dependency is rejected and archived. Compiler,
runtime and loader inventory are restored to `106d92a`; three constant-chain
regressions remain and all1655 restored tests pass. Next investigate bounded
direct-flow regions with staged register writes to amortize native calls.
No new hardware checklist item closes;21/30 remain complete.

| Priority | Candidate | Evidence required before keeping it |
| --- | --- | --- |
| 1 | Physical ns remainder reduction is retained. Watchdog-period caching is rejected. Next prototype lazy watchdog clock synchronization using the completed consumer audit, then fewer repeated event scans/conversions. Equal-rate, bounded-multiply and native-delay guards are rejected. Broader peripheral activity gating remains open. | Preserve the off-state free-running phase, discard inactive history before enabling, keep CPU write-window expiry and eager fault-sensitive paths. Keep integer residues, event/pin/PCM parity, enabled-watchdog/ADC and CLKI controls. Require balanced identical-runtime timing; inspect exact WASM without assigning a cause from static code alone. Repeat IRQ-active browser audio/underrun checks before default activation. |
| 2 | Evaluate adaptive bounded-region instruction budgets near deadlines. Separate inter-block fusion and constant folding are rejected. | Keep full flags, clock-before-commit, external entries and original fallback. Node HQ4 gains1.448x, but browser live audio still underruns; other firmware/event-heavy gains remain unproven. Measure budget changes separately from native scheduler changes. |
| 3 | Validate optional phase-local liveness for default activation when stable performance measurements are available. | The full-context path remains an oracle. Size/parity are established; do not treat noisy median gains as speed evidence. Keep partial execution, reset/faults, SPM and IRQ effects exactly once. |
| 4 | Extend proven direct WASM regions only where measured coverage justifies it; evaluate region SREG liveness independently. | The bounded cyclic register-local path is implemented. Preserve all observable SREG exits, indirect/external-entry fallback, aliases and visible AVR stack state; require real-firmware gains for extensions. |
| 5 | Evaluate reachable-code generation, Flash-region replacement and persistent caching separately from execution optimizations. | Correct dynamic targets and code/data handling, complete SPM dependency invalidation, exact cache identities and independent cold-start/compilation measurements. |

For each candidate, retain the exact baseline and sources, a correctness oracle,
activation evidence, individual paired timings and variance. Reject or archive a
candidate whose benefit is unproven. Keep necessary external CLK transitions and
peripheral events inside the native scheduler even when fewer WASM operations
represent the same AVR instruction span. Device definitions, translator sources
and generated artifacts remain separate.

For execution measurements, preserve identity controls, actual clock-divisor
assertions, equal warmups and balanced run ordering from
`scripts/benchmark-runtime-controls.mjs`. Keep real firmware, direct CPU,
internal/CLKI and enabled-ADC controls. Sampling/instrumented runs remain
separate from speed measurements. The rejected single-service inline hint in
`reports/runtime-controls-20261024.md` is recorded evidence, not a pending
production change or an implemented optimization.

#### Physical nanosecond clock checkpoint (retained)

Physical mode now retains the nanosecond fractional remainder as0..999ps,
denormalizing it for the existing NVM deadline formula. Legacy and watchdog
remainders retain their previous units. All1677 tests and13 parity cases pass;
608 timing runs/304 warmups retain5952 exact snapshots. HQ4 physical gains
1.103x/1.164x across two screens, faster in all16 pairs. Other gains are not
established; a small internal20MHz-kernel loss remains possible under noisy
controls. The longer negative kernel median weakens to0.987x.
Runtime grows74 bytes to117975, with fixed two-page memory and no host imports.
The browser gate is not rerun for this native revision; default engine stays
`wasm`. The model/hardware checklist stays21/30 with nine open. See
[exact sources, measurements and caveats](../reports/physical-ns-remainder-20261025.md).
The separate watchdog-period experiment below did not establish a gain.

#### Watchdog clock checkpoint (period cache rejected; lazy sync audited)

Exact period reduction passes1681 tests and15 parity cases, but four screened
medians0.997x/0.993x/0.976x/0.961x do not establish a gain. Production returns
to the retained117975-byte ps→ns runtime. Four new fraction/reset regressions
and two real watchdog ISR benchmark cases remain;128 timings/64 warmups retain
1824 exact snapshots. See [rejected candidate and reproduction](../reports/watchdog-period-20261025.md).

The next lazy-clock experiment has a [consumer and boundary audit](watchdog-lazy-clock-audit.md).
Do not simply gate `elapse` or the whole watchdog service: enabling must first
discard inactive history, CPU write windows still expire while off, and both
reset/startup implementations consume the oscillator phase. Keep the current
numerator units and eager fault-sensitive arithmetic. Implementation/performance
validation remains open. No hardware item closes:21/30 complete, nine open.

#### Native-delay checkpoint (rejected)

Native-delay checkpoint: native-width phase subtraction passes1674 tests and
the13-case parity matrix, but three paired timing rows1.004x/1.002x/0.993x do
not establish speed gains. The header/runtime are restored and the independent
fraction/product-boundary regression remains. See
[clock-delay evidence](../reports/clock-delay-20261025.md). Its physical ps→ns
follow-up is retained above with NVM/legacy/CLKI/ADC parity. No hardware
checklist item closes.

#### Bounded-region checkpoint (optional implementation)

`boundedRegions:true` now emits cyclic register-only components of at most64
decoded words with up to32 executed instructions per admitted span. All1673
tests and13 parity cases pass. Untimed traces prove activation with active IRQs;
416 timed runs with identity controls/208 warmups show HQ4 physical1.448x, an event-free
synthetic direct loop11.265x and internal audio kernel4.210x. Rhythmic/Lumière,
CLKI and active-ADC gains are unproven. Physical CPU modules grow1.36–1.67%.
The native runtime/default CPU output are unchanged. The option remains off by
default. A subsequent browser screen passes12 parity checkpoints (24 more in
Node replay), but all six10-second audio runs underrun: delivered frames are
26–37% of the requested stream. This is a failed default-engine gate, not a
balanced speed comparison or silicon evidence. See the
[browser record](../reports/bounded-browser-20261025.md). Exact Node sources, controls and
next budget/admission experiments: [report](../reports/bounded-regions-20261025.md).
No hardware checklist item closes:21/30 complete, nine open.

Use the unchanged generated instruction path as oracle. The purpose is to
amortize register caching and native calls across control flow, rather than add
another small peephole pass. Keep this independent of peripheral activity work.

- Start with a bounded number of register-only instructions and direct
  RJMP/conditional/skip edges. Memory/I/O, stack, system operations and I-bit
  changes terminate a region before their effects. Unknown targets use the
  original per-PC entry. Do not interpret AVR opcodes at runtime.
- Guard the whole worst-case cycle/instruction span before staging anything:
  caller budget/deadline, earliest native event, pending IRQ/delay, inactive
  continuation, f64 capacity and retired-counter headroom. A zero-length result
  must return without native clock work. CLKI keeps its existing zero budget.
- Stage dirty GPRs, full SREG, next PC and actual cycle/count totals in WASM
  locals. The prototype preloads the statically used register union once to
  avoid a validity branch on every read; flush only potentially written GPRs.
  ASR must sign-extend the current cached byte. Preserve8-bit writes and
  register-pair aliasing.
- Advance the native clock by the actual original-cycle total, then commit
  staged state/retirement exactly once. Keep clock-before-commit. Reset/fault
  or an unexpected WAIT must discard staged writes and retain fail-closed
  behavior; do not replay native work through a fallback.
- Materialize every architectural register/flag at all external exits. Keep
  original callable instruction entries and observe partial deadlines through
  their existing phase path. Do not combine cross-block flag elimination yet.
- Prove actual region activation and test loops, external entries, short limits,
  all SREG inputs, host edits, bus barriers, IRQ/reset/protected windows, SPM and
  retirement limits. Complete the13-workload parity matrix before timing.
  Keep default bytes unchanged until correctness and performance gates pass.

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
  manufacturer definitions; do not invent one. The2026-10-24 admission audit
  found DWEN was rejected only with the optional analog RESET receiver; other
  profiles incorrectly accepted it as ordinary RESET. Native init, the public
  runtime and all package versions now reject programmed DWEN independently of
  that receiver, RSTDISBL and lock bits. This closes the silent fallback, not
  debugWIRE support: documented PB5 mux behavior, cold-start/debug state and
  sleep-clock behavior still need a complete supported contract. See the
  [interface inventory](devices/attiny13a/interfaces.md).
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

Timer0 diagnostic/probe checkpoint, 2026-10-24: all1194 default regression tests
pass, including six new generated-CPU boundary cases and one PB4/T0 routing
regression. The module's pending-OCR3 transition no longer invents a pulse from
active TOP=0; clock-free holds remain supported. All12 source-only probe profiles
assemble, four nonzero controls execute and five Python protocol checks pass.
The112642-byte native runtime has103 function exports plus memory, no imports
and fixed two-page memory. The [integration report](../reports/timer0-integration-20261024.md)
retains before/after evidence, commands and the software-only probe identities.
The checklist remains21/30 complete with nine open; no hardware measurement or
TOP=0 implementation is claimed.

Acquisition tooling checkpoint, 2026-10-24: CLKPR12/RESET4/ADC9 new profiles
compile to204–614 Flash bytes, with zero data/BSS. All25 actual firmware images
produce59 decoded frames through the full generated CPU/native board. Protocol
checks pass15/15 plus the existing Timer0's5/5. 40 additional ADC runs retain80
trial results with both ideal step directions; first-sample27/29 choices differ
at tested118–124us marker offsets while warmed controls agree. These establish
probe sensitivity, not an observed silicon aperture. Native runtime and library
bytes are unchanged from the preceding1194-test checkpoint. The checklist
remains21/30 complete with nine open. Next hardware work is actual acquisition
and the remaining internal bus/stack-phase audit; independent performance and
cache work can proceed while physical measurements are unavailable.

## Primary references

- [ATtiny13A Data Sheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
- [AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
- [WebAssembly Core binary instructions](https://webassembly.github.io/spec/core/binary/instructions.html)
- [Microchip ATtiny DFP3.4.278](https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack)
- [Imported manufacturer definitions and provenance](../vendor/microchip/ATtiny_DFP/3.4.278/README.md)
- [Current instruction mapping and runtime contract](AVR_TO_WASM.md)
- [Device bus and scheduler contract](peripherals/device.md)
