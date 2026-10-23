# Timestamped CLKI and resumable CPU design

Status: **implementation open**. This document proposes a contract; it does not
add CLKI support or change the supported hardware scope. Audit baseline:
`abd0cfe3686c195f5aba3806184a239c295ae8e8`. The scope is execution of an already
loaded ATtiny13A image. External programming protocols are outside this design.

The required behavior includes an external clock held indefinitely high or low,
resumption after a host return, and an instruction suspended between its existing
bus phases. Period-only clock configuration is not a substitute for this scope.

## Official evidence and its limits

Source: Microchip **ATtiny13A Data Sheet DS40002307A**, 2021; page numbers below
are printed PDF pages, not the outdated table-of-contents page numbers.

- **S1:** CKSEL=00 selects CLKI; PB3 carries CLKI.
  [Sections 6.2.1 and 10.3.1, pages 30 and 62](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=30).
- **S2:** CLKPR divides all synchronous domains by 1..256; CKDIV8 initializes
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

These references do not specify the pad-to-system-clock propagation, the initial
divider phase, or a universal CLKI polarity/latency mapping. In particular, S2
does not justify promising the exact lower-bound transition for silicon. S3
does not justify promising arbitrary hot stop/restart as electrically qualified.

## Two explicit profiles

The **digital fixture** provides deterministic edge delivery, clock holding,
phase retention and resumption. Its phase policy is a named, versioned model
parameter, proposed as `digital-noninverting-zero-seed-v1`. For division by one,
it maps source levels to system levels without an invented delay. For larger
divisors it counts source rising edges, using a specified counter seed and
output level. Reset/release and Power-down wake must specify how that seed is
established; a software reset must not silently move wall time or fabricate a
pad edge. This policy is testable software behavior, not a measured chip phase.

An optional **electrical validation profile** checks S3 separately. It must
report an out-of-profile/uncertain waveform rather than synthesize a plausible
CPU result. Ideal level transitions assume zero slew; real threshold crossing,
rise/fall, noise and metastability require explicit input qualification and
hardware validation. Source-period checking and the post-CLKPR operating-speed
check are separate: division cannot repair an invalid pad waveform by itself.

The frequency-versus-period discrepancy in S3 must remain visible. A strict
fixture may require both relative tests, or expose which definition it checks;
it must not silently equate them near the boundary. Compare integer ratios
without overflowing uint64 timestamps. Missing edges and hot restart retain
state in the digital fixture; their silicon validity is not inferred merely
from the zero-frequency entry. Large period changes under an effective,
recognized Reset need a defined new comparison baseline after release.

PB3 is shared with GPIO/ADC3/PCINT3. A CLKI event must describe the same physical
pad used by pin capture, not a second invisible clock wire. The current GPIO
model has no CLKI ownership setting. Do not invent a DDB3/PORTB3 override from
the function name: Table 10-4 does not spell out such a clock override. An
initial safe fixture requires PB3 input configuration; output contention is
explicitly unsupported/uncertain. The clock receiver must not accidentally
depend on PINB synchronization or DIDR0's GPIO read clamp. Any later electrical
or alternate-function model needs its own evidence.

## Time and input stream

Use the existing uint64 **physical picosecond** timeline for wall time. Enable it
for an external-edge profile independently of an OSCCAL table: the latter
describes the internal RC source and must not become a dummy prerequisite.
Legacy `baseHalf` remains its existing unit and cannot be reinterpreted.

Keep distinct state for wall time, source input level/edge count, divider
phase/output level, and delivered system half-phases. Wall time can advance
with no source edges. A clock hold advances no synchronous phase; WDT, power
observation, recognized Reset, NVM wall latency and audio deadlines still run.
Sleep domain gates remain separate from source presence: source input events
can arrive while their downstream domains are gated.

An edge is `(timePs: uint64, level: 0|1)`, with an explicit initial level. Require
strictly increasing transition timestamps; reject a duplicate level or conflicting
same-time level as malformed input without consuming a CPU phase. Do not create
an artificial first edge at time zero. Initial CPU instruction admission waits
for the profile's defined system phase.

The producer also declares a monotonically increasing **known-input horizon**.
All CLKI transitions up to that horizon are already queued; an empty interval
means the last level is held. Once time has been consumed, no insertion into the
past is allowed. If the next host deadline exceeds the horizon, return
`WAIT_INPUT` at the horizon, not an extrapolated period. A declared, edge-free
interval lets `runUntilPs` reach its exact endpoint while the CPU stays suspended.

Periodic segments are only a compact producer of this same stream: explicit
`startPs`, initial level, `highPs`, `lowPs`, and finite end/stop. They preserve
integer event timestamps and a rational remainder if requested, rather than
round-tripping through a single floating-point Hz. Arbitrary edge streams remain
the authoritative supported contract. Batch input avoids per-edge host imports.

Queue limits must return backpressure before accepting a partial batch; queue
overflow must not silently drop clock transitions. Prefer one chronological
event merge for CLKI, GPIO, analog and VCC, or merge separate queues by exact
timestamps. Preserve order independently of host batch boundaries.

## Proposed C boundary

Names and signatures are proposed, not implemented ABI commitments:

```c
typedef enum {
    DEVICE_CLOCK_COMPLETE, DEVICE_CLOCK_WAIT_CLOCK, DEVICE_CLOCK_WAIT_INPUT,
    DEVICE_CLOCK_RESET, DEVICE_CLOCK_FAULT
} device_clock_result_t;

int device_configure_clki(const device_clki_profile_t *profile); /* before init */
int device_inject_clki_ps(uint64_t at_ps, uint8_t level);
int device_declare_clki_horizon_ps(uint64_t known_until_ps);
uint64_t device_next_clock_edge_ps(void); /* UINT64_MAX: none queued */
uint64_t device_clock_available_halves_ps(uint64_t deadline_ps);
device_clock_result_t device_clock_advance_ps(
    uint64_t requested_halves, uint64_t deadline_ps, uint64_t *consumed_halves);
```

`available_halves` is a **floor of guaranteed deliverable phases**, respecting
queued edges, divider transitions and gates. It is not the current ceil estimate
from Hz. `clock_advance` consumes at most the requested phases and never crosses
the supplied wall deadline. It returns the consumed count even on suspension.
The CPU continuation owns the remaining count; the board must not charge it
again on retry. `WAIT_CLOCK` is normal suspension, not an error or Reset. The
host can distinguish it from an exhausted input horizon.

If the last required edge is exactly at the deadline, return COMPLETE and apply
its eligible post-barrier effect in that same invocation before returning to
the host. Do not let an outer `TIME >= deadline` check postpone an OUT, stack
write or retirement to the following call. Zero-duration trailing/commit stages
must also finish without asking for another clock. Recognized Reset retains
the tie priority described below.

Existing `.step()`/`.clock()` methods have no wall deadline and cannot wait
indefinitely for unspecified future transitions. In this profile they must
return an explicit WAIT without inventing missing phases, reject the unbounded operation,
or expose a bounded `stepUntilPs`/`clockUntilPs` replacement. They must not
silently consume a future edge beyond the caller's observation boundary.

An additional board advance-to-wall-deadline operation must work even when the
CPU is clock-starved but not asleep. Do not reuse the unchanged
`while (device_halted())` condition in current `wait_until`: clock starvation and
a pending instruction are new execution states. All advances still stop at a
recognized asynchronous Reset and let the CPU bridge acknowledge it.

`device_cpu_half_deadline_ps`, `device_cpu_halves_until_ps` and
`device_next_cpu_event` need external-profile implementations based on actual
known phases; an unavailable absolute event time is `UINT64_MAX`, not a guessed
Hz conversion. Return a conservative zero batching budget when proof is missing.
Invalidate the deadline cache on CLKI enqueue, horizon publication, source/domain
gate changes, divider transition, reset/release and each serviced event.

## Event ordering and clock domains

At a wall timestamp, first advance independent elapsed-time domains without
inventing system phases. A recognized Reset cancels the CPU continuation before
any later CPU effect. CLKI transitions then cause eligible system edges; those
edges drive GPIO synchronizers, Timer0 and ADC prescalers through the existing
domain gates. Ordinary equal-time pin/analog injections retain the current
documented after-sampling convention. CLKI is itself the cause of sampling and
cannot be treated as an ordinary pin update applied after that edge.

Specify an explicit tie rule for a recognized Reset coincident with a clock
edge: proposed digital profile gives Reset priority. This is deterministic
fixture ordering, not an analog setup/hold guarantee. Do not let queue insertion
order choose it. At an effect boundary, apply the previously latched bus value
once, after the required phase has actually been delivered.

The GPIO falling-edge latch must use the real delivered edge. A half-phase is
an edge-count domain here, not half of an average clock period; this preserves
unequal high/low durations in the division-by-one fixture. Divider transitions
must be scheduled by source-edge state, retaining the current documented
lower-bound fixture as an explicit policy where applicable. They cannot be
scheduled by multiplying a last measured period after the source stops.

## Startup, wake and Reset

Represent startup as separate components: independent WDT timeout/recovery
deadlines, remaining source CK, and remaining divided CPU wake cycles. The
digital fixture may keep the baseline's documented ordering, but must name that
ordering rather than present a single calculated wall deadline as hardware fact.

When the source is held, a source-CK component cannot finish. A WDT timeout can
finish, but does not manufacture its missing source cycles. A startup deadline
getter returns `UINT64_MAX` while the necessary future edges are not known; an
explicit remaining-CK/status getter is more useful than a predicted frequency.
Power-down wake arms its source-CK stage at the wake request. Idle/ADC sleep
retain their existing domain-specific gates and do not restart a source startup
stage. The divided extra wake delay counts actual eligible system edges.

Audit the one-CK WDT reset pulse too: its end must not be a fabricated
`source_duration(2)` wall deadline with an absent CLKI source. Reset aggregation
must have exactly one owner. The separate Reset receiver qualifies assertions;
the clock owner times source-dependent release/startup components. NVM/WDT wall
time continues through all these states according to its selected profiles.

## Persistent translated CPU continuation

Current generated instruction functions cannot return midway and resume their
WASM locals. Persist a continuation in shared memory, or compile explicit
phase-entry functions with persistent fields. Proposed minimum state is:
`active`, `execPc`, latched operation/parameters and generation, `stage`,
remaining half-phases, `nextPc`, staged flags,
latched operands/read results/address, and instruction-specific bookkeeping.
Reserve a separate IRQ-entry continuation. The state is part of runtime ABI and
must have bounds/provenance validation in portable packages.

Prefer the stable native memory/layout over generated-module-only globals:
`ATtiny13A._refreshFlash()`/`_compile()` can replace the translated WASM module.
Recompilation must neither lose the active context nor reinterpret it as the
new instruction now stored at `execPc`. Retain the old continuation code until
retirement, or use a stable operation recipe independent of the replacement
page's opcode. Bind/invalidate idle metadata without replaying an active SPM.
If external-profile lowering changes generated code, its capability must be in
the runtime ABI and compilation/cache key; configuration-dependent code cannot
reuse an incompatible existing cache entry.

At every clock barrier, first make the continuation resumable, then consume
phases. On WAIT, return without the next effect. On COMPLETE, execute that
phase's effect exactly once and advance its stage. Resume an active instruction
before fetching another opcode. IRQ acceptance stays at a retired instruction
boundary. Instruction counts include only retirement, not attempted steps or
resumptions.

The native wait bridge currently invokes `full_interrupt()` after waiting.
Clock-starved wall polling must not accept an IRQ during an active instruction
or IRQ-entry context. It may recognize Reset; IRQ arbitration resumes only at
the eligible instruction boundary with delivered CPU phases.

The following baseline details need explicit migration:

| Baseline location | Required continuation behavior |
| --- | --- |
| `avr-transpiler.js:277` writes PC+1 in the prologue | Keep `execPc` and pending `nextPc`; publish architectural PC at retirement. |
| `effects()` branches/jumps and CLI/SEI/FLAG, lines 209..222 | Delay target/flag publication until its required phases complete. |
| IN/SBIC/SBIS, lines 217..218 and 244 | Persist the read value between the existing read and completion barriers; do not read twice. |
| LDS/LD, lines 248 and 256..262 | Persist address, operand and read result; pointer updates occur once at their modeled phase. |
| PUSH/POP/CALL/RET, lines 227..241 | Retain completed stack writes/reads and SP changes; resume the next phase without replay. |
| LPM, lines 267..273 | Consume special RFLB recognition once at instruction start; persist returned data until completion. |
| SPM/EECR control and returned stalls | Issue the request once; suspend the remaining wait/stall, not the command itself. |
| `avr-device.inc:65..72` IRQ entry | Persist vector, return PC, start time and stage; acknowledge vector and update frames only at completion. |

On Reset, discard all pending CPU/IRQ contexts **before any stale spill can
overwrite reset state**. Keep SRAM effects already committed at earlier phases;
do not roll back a partial stack operation. Reset supersedes uncommitted PC,
register and flag effects.

Initially disable translated BLOCK execution and fastIdle in this profile.
`avr-transpiler.js:325..352` currently applies all effects before one clock call,
so its event budget is insufficient for a suspendable clock. Re-enable batching
only with proof that every included phase/effect is covered by a known interval
and cannot cross a Reset/event barrier. This design retains direct translated
WASM operations; it does not add an opcode interpreter or a JavaScript callback
for each phase.

## Code touchpoints after implementation is authorized

- `native/peripherals/device.c/.h`: independent wall advancement; CLKI stream,
  divider state, edge-based deadline mapping, startup counters, domain gates and
  explicit WAIT result. Replace the constant-rate assumptions in `at_half`,
  `elapse`, `reset_startup`, `wake` and CPU deadline helpers for this profile.
- `native/peripherals/system_gpio.c/.h`: deliver actual rising/falling edges;
  explicit PB3 clock-input coordination and its unresolved output case.
- `native/peripherals/system_sleep.c/.h`: phase-count wake progress rather than
  a wall deadline derived from a frozen frequency.
- `native/avr-device.inc` and the native ABI/layout: persistent CPU/IRQ contexts,
  bounded host-call deadline, COMPLETE/WAIT/RESET distinction and elapsed-time
  advancement while starved. The existing error26 Reset path alone is inadequate.
- `lib/avr-transpiler.js`: resumable phase IR/entry points and retirement commits;
  disable unproved blocks/idle acceleration. Every save/restore must preserve
  exact SREG, including flags omitted by optimization until demanded.
- `lib/attiny13a-runtime.js`: batched edge/horizon APIs, exact `runUntilPs`
  suspension/resumption, and returned status. A valid hold must not trigger the
  current "Device stopped before the physical deadline" exception.
- `lib/attiny13a-package.js`: versioned clock/phase/electrical profile and ABI
  checks; physical time no longer inferred solely from a non-null OSCCAL table.
  Register addresses and memory geometry continue to use the official DFP maps.

Audio samples retain fixed wall deadlines and integrate the last pin levels
during a hold. No instruction may overshoot a capture deadline merely to find
its next clock edge. Rebased f64 runner offsets remain bounded; absolute edge
timestamps and exported state remain uint64, including times above 2^53 ps.

## Required acceptance cases

1. A source held high and held low each advances wall time without retiring
   an instruction; WDT, power events and NVM completion still occur.
2. Every instruction clock barrier can return and resume, with identical final
   state/event timestamps to a single uninterrupted run of the same stream.
3. Suspend immediately before/after IN/LDS/LD reads, stack phases and RFLB
   recognition. Read side effects, writes, SP changes and command requests occur
   exactly once; no later register/PC/SREG effect becomes visible early.
4. Reset during each CPU/IRQ phase cancels the remainder and preserves only
   already committed SRAM. Cover equal-time source edge/recognized Reset.
5. Division-by-one unequal high/low phases drive GPIO latching at their actual
   timestamps. Divider profiles exercise every supported CLKPR factor and a
   transition followed by a source hold.
6. Reset and Power-down wake cannot finish their CK stages without source edges;
   independent WDT timeout does finish. Idle/ADC paths retain the intended gates.
7. Whole-stream, random batch and one-edge-at-a-time feeds agree, including
   backpressure, known-input horizons and exact large timestamps.
8. Electrical-profile boundary cases cover each S3 range, period/frequency
   ambiguity, slew assumptions, output contention and changes while Reset held.
   Out-of-profile results are explicit; no silicon corruption pattern is invented.
9. Audio at a low/stopped source samples constant pins with exact deadlines;
   a later clock resume changes only subsequent applicable sample intervals.
   An eligible OUT exactly at a sample deadline commits in the same host call;
   Reset at that timestamp cancels its still-pending effect by the tie rule.
10. Existing fixed-source/OSCCAL tests remain compatible. Portable package ABI
    validation rejects a translated continuation layout the runtime cannot resume.
    Flash recompilation preserves or safely finishes an active old-generation
    continuation; unbounded step/clock APIs cannot hang or fabricate progress.

No items above are implemented by this documentation-only change.
