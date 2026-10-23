# Timestamped CLKI and resumable CPU contract

Status: **native source, board, CPU/IRQ and package integration implemented**.
The initial design audit at
`abd0cfe3686c195f5aba3806184a239c295ae8e8` described disconnected building
blocks. Integration checkpoint `801b7fd` connects them; `4f1261b` supplies the
finite periodic producer. Those historical audit statements are not current
limitations. This document describes the implemented digital contract, not a
claim that the latest combined test suite has completed.

The scope is execution of an already loaded ATtiny13A image, including a source
held high or low and an instruction suspended between bus phases. ISP and HVSP
are excluded by [the project scope](../../EMULATION_SCOPE.md).

## Official evidence and its limits

Source: Microchip **ATtiny13A Data Sheet DS40002307A**, 2021; page numbers below
are printed PDF pages, not the outdated table-of-contents page numbers.

- **S1:** CKSEL=00 selects CLKI; PB3 carries CLKI.
  [Sections 6.2.1 and 10.3.1, pages 30 and 62](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=30).
- **S2:** CLKPR divides synchronous domains by 1..256; CKDIV8 initializes
  division to eight. Switching produces two active edges within T1+T2..T1+2T2;
  ripple phase is not predictable.
  [Sections 6.3..6.4.2, pages 32..34](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=32).
- **S3:** External limits:

  | VCC range | Maximum frequency | Minimum period | Minimum high/low | Maximum rise/fall |
  | --- | --- | --- | --- | --- |
  | 1.8..5.5 V | 4 MHz | 250 ns | 100 ns | 2.0 us |
  | 2.7..5.5 V | 10 MHz | 100 ns | 40 ns | 1.6 us |
  | 4.5..5.5 V | 20 MHz | 50 ns | 20 ns | 0.5 us |

  Minimum frequency is zero; duty need not be 50%. Table 18-3 limits consecutive
  period changes to 2%; section 6.2.1 instead says frequency changes, requiring
  Reset for larger changes.
  [Page 125](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=125).
- **S4:** Idle gates CPU/Flash; ADC Noise Reduction also gates I/O; Power-down
  gates generated clocks. External startup uses 6 source CK; reset adds 14 CK
  and SUT-selected 0/512/8192 watchdog ticks; SUT=11 is reserved.
  [Pages 30..31 and 36..37](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=31).

These references do not specify pad-to-system-clock propagation, initial
divider phase or a universal polarity/latency mapping. S2 does not establish
the exact lower-bound transition as measured silicon behavior. S3 does not
qualify arbitrary hot stop/restart waveforms merely by listing zero frequency.

## Selected digital phase and optional validation

The required profile is
`{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:0|1}`.
It requires CKSEL00, `resumable:true` and physical picosecond time. No dummy
OSCCAL table is needed for CLKI. The optional third field
`electricalValidation` is `none` by default or `datasheet-ideal-v1`.

The divider starts with counter zero. Division by one starts at the supplied
source level and follows actual alternating transitions. Other divisors start
low and toggle every D/2 source rising edges; source falling edges do not
consume the residue. No midpoint is invented for unequal high/low durations.
Initial alignment establishes the CPU phase without fabricating a transition
or charging a completed CPU half-phase. A hold preserves phase. A gated main
clock tracks the input level while freezing output, residue and pending divider.

CLKPR requests become active at the next old system rising transition, keeping
that output high and resetting its residue. A firmware request at a retirement
rising edge therefore uses the explicit T1+T2 lower-bound fixture. A request
during a hold remains pending until the required real edge. Reset reconfigures
the divider without fabricating an output transition. See
[the divider contract](clki_clock.md) for the precise rules.

The source drives the same PB3 pad observed by GPIO, ADC3 and pin capture.
Separate digital/analog PB3 injection is rejected; driving DDB3 as output
reports an explicit CLKI fault. The fixture does not infer an undocumented DDR
override from the alternate-function name. Clock reception does not depend on
the synchronized PINB value or its DIDR read clamp.

Optional `datasheet-ideal-v1` validation assumes zero-slew logical transitions.
It checks completed high/low widths and periods against S3's supply tier and
conservatively checks both 2% interpretations. The board supplies the worst
observed supply tier over a completed interval. Effective Reset clears the
variation baseline; it does not waive voltage or width limits. Violations fault
before later CPU effects. This remains separate from post-divider CPU speed:
division cannot repair an invalid pad waveform. See
[the validator contract](clki_validation.md).

Neither profile measures analog threshold crossings, slew, noise, metastability
or silicon phase. Receiver parameters, hardware phase and hot stop/restart
qualification remain unmeasured.

## Time, queue and finite periodic production

Wall time is uint64 physical picoseconds, with `UINT64_MAX` reserved. Source
level, divider phase, delivered system halves and wall time are distinct state.
WDT, supply/reset observation, NVM wall latency and audio deadlines continue
while the source is held. Sleep gates do not erase or replace the source stream.
Legacy `baseHalf` remains its earlier unit and cannot be used for this profile.

`injectClkiPs({edges,knownUntilPs})` submits an atomic batch of
`{timePs:bigint,level:0|1}` transitions. Timestamps strictly increase, levels
alternate, and every new edge is strictly after the previously published
inclusive horizon. The new horizon covers the batch and cannot move backward.
Initialization declares a level, not a synthetic edge at time zero.

The native queue holds 512 edges. Backpressure returns `false` without a partial
batch or horizon update; malformed input throws. An empty batch extends a known
high/low hold, including while the queue is full. A declared horizon promises
that all transitions through that endpoint are known. It cannot later be revised
by inserting another edge in that interval.

`injectClkiPeriodicPs` accepts exact integer-picosecond `startPs`, `highPs`,
`lowPs`, finite BigInt `transitionCount`, explicit `initialLevel` and
`knownUntilPs`. Durations are positive; the initial level must match the
already-declared tail. Start is at or after the old horizon. The first edge is
`startPs + (initialLevel ? highPs : lowPs)`; there is no edge at start. The
horizon must cover the last actual edge. Count zero is a known hold. Exhaustion
holds the last level and never extrapolates another transition.

The finite descriptor lazily refills the same 512-edge queue in C, allowing
longer signals without a JS call for each edge. While descriptor edges remain
unmaterialized, another descriptor or nonempty raw batch returns backpressure;
an empty batch may extend its horizon. `periodicRemaining` counts those
unmaterialized edges, separately from `queued`. All externally observable source
edges are still serviced by the scheduler: this is compact production, not an
O(1) analytical skip of clock/peripheral work. There is no floating-point Hz or
fractional-duration option in this producer.

Host usage and a periodic example are in the
[package/runtime guide](../../../lib/attiny13a-package.README.md#resumable-cpu-and-digital-clki-stream).

## Native boundary, event ordering and startup

The board implements `device_configure_clki(field,value)` before initialization:
field 0 enables CLKI, field 1 explicitly sets the initial level, and field 2 enables
ideal validation. `device_clki_enqueue` and `device_clki_periodic_ps` publish
input; getters expose horizon, level, queue/free counts, remaining producer
edges, alignment, remaining startup CK and status. Native WASM bridges expose
these operations to the host; there are no per-edge host imports.

`device_advance_half_until_ps(wanted,deadline,&consumed)` reports actual delivered
whole halves: 1 COMPLETE, 0 WAIT, or -1 RESET/FAULT. The CPU continuation retains
the unconsumed span. `COMPLETE`, `WAIT_CLOCK` and `WAIT_INPUT` source statuses
distinguish a fulfilled span, a known hold/clock wait, and an exhausted horizon.
No average-frequency conversion invents missing phases. CPU batching receives
a conservative zero event budget for this source.

At each timestamp the board advances independent wall-time domains and handles
recognized Reset/supply inputs before a coincident clock effect. CLKI updates
PB3 and delivers eligible edges through the divider and domain gates. GPIO's
falling/rising sampling uses those real delivered edges; Timer0/ADC receive their
enabled clock domains. Ordinary equal-time GPIO/analog inputs retain the
after-sampling convention. The ordering is deterministic fixture behavior,
not an analog setup/hold guarantee.

Reset and wake progress have separate watchdog-time, source-CK and divided
CPU-cycle components. With `fuseStartupProfile:1`, reset waits the selected
watchdog timeout followed by 20 source CK (6+14). Power-down wake counts its
source startup CK, followed by the modeled divided wake cycles. Idle/ADC sleep
retain their domain-specific gates. The optional `wakeStartupHalf` fixture must
be even for CLKI so its source-CK count is explicit. A held source cannot finish
a CK stage, even if a watchdog timeout or BOD recovery has completed.

The watchdog reset pulse ends on a subsequent real source CK; it is not timed
from a last measured period. Reset aggregation owns recognition/hold, while the
source owner counts clock-dependent release/startup. An unavailable startup
wall deadline is `UINT64_MAX`; `startupCK` exposes remaining source work instead
of a frequency prediction. CPU reset preserves the external source queue and
monotonic physical timeline.

## Persistent CPU/IRQ and host behavior

The [80-byte continuation](cpu_phase.md) lives in native shared memory, surviving
returns and translated-module replacement. Generation-time CLOCK markers lower
to direct WASM control and saved locals; no opcode interpreter or JS callback
executes phases. Each WAIT retains read latches, operands, remaining halves and
the next stage. Resume skips completed effects. PC/SREG commit at retirement;
instruction counts include completed retirements only. IRQ entry has its own
resumable C2/C3/C4 stages and does not decrement SEI/RETI delay during polling.

Recognized Reset cancels CPU/IRQ context before stale locals can be spilled.
Already committed SRAM writes remain; pending register/PC/flag effects do not.
An effect or zero-clock retirement tail whose required phase ends exactly at
the deadline can commit in that call, subject to Reset priority. Flash refresh
waits for active old-generation work to finish before another instruction fetch.
Translated blocks and fastIdle are disabled in resumable mode.

`runUntilPs` is bounded and returns a retirement count. It reaches a known hold's
deadline without inventing CPU progress; when its requested deadline exceeds
the known horizon it returns earlier with `state().clki.status==='WAIT_INPUT'`.
Extend the input and call again to resume. Unbounded `step`, `run`, `clock`,
`interrupt` and `runBlock` are rejected with CLKI selected. Host EERE/EEPE command
writes are also rejected; firmware issues those commands with resumable stalls.

Physical audio integrates held pin levels on its wall-time sample grid. It
preflights the full requested capture horizon before changing CPU/audio state,
reporting explicit `CLKI WAIT_INPUT` if input is insufficient. Absolute times
remain uint64, with rebased exact f64 offsets for bounded WASM runner calls.
Package v5 records the initial CLKI profile and execution mode and validates
the phase/source ABI; it is not a saved queue, producer or in-flight continuation.

## Verification entry points and remaining qualification

Tests are separate evidence for the digital contract; this documentation update
does not assert completion of the latest combined run. Relevant suites include:

- `attiny13a-clki-{input,clock,periodic,validation}.test.mjs`: standalone atomic
  queue/horizons, all divider factors/transitions, exact finite production and
  ideal timing boundaries.
- `attiny13a-clki-{board,sleep,runtime,periodic-runtime}.test.mjs`: shared PB3,
  source holds/resume, divider/startup/sleep/reset, coupled peripherals, bounded
  CPU/audio and periodic/raw equivalence.
- `attiny13a-cpu-phase-native.test.mjs`, `avr-resumable-runtime.test.mjs` and
  `avr-resumable-oracles.test.mjs`: CPU/IRQ WAIT stages, read latches, once-only
  commands, exact deadlines and reset cancellation.
- `attiny13a-clki-host.test.mjs` and package suites: input validation,
  backpressure, v5 ABI/configuration and historical format compatibility.

Hardware traces are still needed to qualify the chosen phase seed, internal
stack/bus phases, analog source reception and physical stop/restart behavior.
Optional ideal validation and digital parity tests do not establish that
measurement. External programming interfaces remain outside the scope.
