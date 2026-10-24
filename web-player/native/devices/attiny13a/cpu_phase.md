# Native ATtiny13A CPU continuation contract

This is an optional physical-time execution backend. It does not decode guest
opcodes or change the legacy executor. The translated emitter owns instruction
effects, PC/SREG commits and its saved locals/stage. Native code supplies bounded
clock spans, asynchronous reset cancellation and resumable interrupt entry.
Both the internal physical clock and the timestamped CLKI board source use
this backend. The original native-only checkpoint preceded CLKI integration;
that historical boundary no longer describes the current runtime.

## Stable context and exports

Call `avr_device_phase_enable(1)` before the first `avr_reset`. It returns1 for
pre-init values0/1 and0 for an invalid value or a late configuration. Enabling
requires a physical1ps board profile, selected by an explicit OSCCAL table or
the digital CLKI profile; a fixed oscillator legacy timebase is rejected on
reset. The enabled choice survives a subsequent cold reset; the context,
retirement counter and deadline are cleared by that reset.

`avr_device_phase_layout(item)` returns absolute WASM-memory addresses:

| Item | Value | Context byte offset/type |
| --- | --- | --- |
|0|context pointer|—|
|1|80, context size|—|
|2|`active` address|0, u32:0 idle,1 instruction,2 IRQ|
|3|`exec_pc` address|4, u32 word PC|
|4|`next_pc` address|8, u32 word PC|
|5|`stage` address|12, u32|
|6|`remaining_halves` address|16, u64|
|7|`locals[9]` address|24, nine i32|
|8|`temp` address|64, double|
|9|`retired` address|72, u64|

The u32 padding at60 is reserved. C static assertions and a compiled layout test
check the80-byte layout. Unknown items return0. `avr_device_phase_active()`
returns the active code, or0 when the backend is disabled.

After rebasing the host-call time origin, call
`avr_device_phase_deadline(relative_ps)` with an exact nonnegative integer
offset no larger than2^53−1; Infinity explicitly selects an unbounded internal
operation. Invalid values or overflowing absolute deadlines report error25.
The emitter must establish this deadline for each host entry/slice.

`avr_device_phase_clock(cycles)` returns1 COMPLETE,0 WAIT or−1 RESET/FAULT.
It accepts nonnegative integer or half-integer cycles, at most4294967295.
An existing pending span resumes; it is not initialized again from `cycles`.
New spans initialize `remaining_halves=cycles*2`. Fractional wall-clock progress
is retained by the board, while only actual whole virtual halves are deducted.
WAIT is normal and does not set error26 or retire an instruction. A zero-cycle
clock can complete at the exact wall deadline, allowing the emitter to perform
the trailing effect/retirement of a completed stage at that same timestamp.

After committing staged architectural PC/SREG/register effects, call
`avr_device_phase_retire()` exactly once with active1 and no remaining span.
It increments `retired`, clears instruction activity and performs interrupt
arbitration once. It does not recommit PC from `next_pc`. Neither ready checks
nor mid-instruction waits decrement SEI/RETI's `irqDelay`.

## Bounded board clock

`device_advance_half_until_ps(wanted, wall_deadline, &consumed)` returns the same
1/0/−1 statuses. It requires physical time, accepts UINT64_MAX as an unbounded
wall limit, and reports an actual floor-counted virtual-half delta. It stops at
the wall bound, all requested halves, reset or fault; reset hold/startup/recovery
returns WAIT without consuming CPU work. A pending CLKPR change is a separate
boundary, after which the remaining target time is recomputed. This preserves
clock phase through a partial internal-clock period and prevents rounding a bus
effect early. CLKI instead consumes actual queued source/divider edges, never a
frequency estimate. A known high/low hold preserves the remaining span while
independent wall-time events continue. An exhausted input horizon returns WAIT
at that earlier bound, with native CLKI status `WAIT_INPUT`; a known clock wait
reports `WAIT_CLOCK`. Unavailable future source phases are not charged to the CPU.

A zero-clock trailing span completes even if SLEEP just started BOD wake
recovery, so that the instruction can retire before the halted-board wait loop
runs. It flushes current-time events and rechecks fault/reset afterward. Physical
reset holds and reset startup still block CPU work; a reset request cancels the
context rather than permitting the zero-clock commit. Nonzero spans remain
blocked during BOD recovery.

## Interrupt and reset behavior

IRQ acceptance saves the selected vector, return PC and start cycle privately.
It clears I and sets active2. Entry resumes through three native stages: two
cycles then the low return-byte push; one cycle then the high-byte push; one
cycle then acknowledgment/vector/frame bookkeeping. Ready and wait may resume
these stages, but do not count an IRQ entry as a retired instruction.

[Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections4.7.1/9, specifies the four-cycle interrupt response and stack use. It
does not guarantee those individual internal SRAM phases; C2/C3/C4 is the
existing explicit digital convention, now retained across host deadlines.

A reset cancels active instruction and IRQ context before returning to the
caller, resets PC/SREG/SP and prevents later bus effects. The monotonic retired
count survives a CPU reset and is cleared only by a cold `avr_reset`.
`phase_clock` returns−1 for reset with ERROR clear; callers must abort without
spilling stale locals. A peripheral fault remains error25 and returns−1.
Current-time digital/analog/VCC injections use the same cancellation path.

An active instruction remains ready even after its SLEEP/SPM controller halts
the board or Flash generation changes: it must finish its already-latched work.
No new instruction may be fetched on generation mismatch; finish any accepted
IRQ, then bind/retranslate before another fetch. Mid-instruction waits do not
arbitrate an IRQ. Native idle-loop skipping is disabled only in this optional
backend, avoiding retirement bypass. Disabled mode preserves the old fast path.

## Generated WASM and JavaScript entry points

`ATtiny13A` accepts `resumable:true` together with an explicit `osccalHz` physical
clock table for the internal source, or a `clkiProfile` for CKSEL00. CLKI enables
physical time without a dummy RC table. This optional mode is disabled by default;
the legacy ABI and retained firmware bytes stay unchanged. The shared emitter
adds clock markers while generating effects; `lib/avr-wasm-phases.js` lowers
those top-level markers into native WASM stage tests and local saves. Clock
markers nested in a conditional are rejected during generation. There is no
AVR opcode interpreter or opaque binary-to-continuation rewrite at runtime.

Each instruction context owns its word PC, staged next PC, stage and saved
operands. A WAIT returns through WASM `return` after saving nine i32 locals and
one f64 temporary in linear memory. The next call dispatches the latched word
PC, restores locals and skips completed prefixes. A reset return skips the
spill, preserving the native cancellation. Architectural PC/SREG commit before
the single native retirement call. All flags are live at an observable
instruction boundary; dead flags can be removed inside an accepted block.
Idle skipping remains disabled in this mode.

Register-only blocks use the same80-byte context and existing native imports.
Their entire original cycle span must lie strictly before the next device/input
event and the host's physical observation deadline. Active continuations,
pending enabled IRQs, SEI/RETI delay and insufficient instruction budget reject
a block. Memory/I/O instructions retain their individual bus phases. CLKI
continues to expose a zero block budget, retaining every source phase and input
horizon. No clock edge or peripheral event is omitted by CPU batching.

An IRQ ready level does not reject a register-only block while SREG.I is clear:
these operations cannot enable I. Peripheral flags and event processing stay
live, and all exit flags remain exact. This follows DS40002307A section4.3.1;
global masking does not make arithmetic flags dead. The run/runUntil loops
already establish the deadline and call native ready before dispatch, so their
internal block attempt uses the guarded function table directly. The exported
block entry retains its full deadline/readiness checks for independent callers.
Invalid PCs still take the ordinary instruction error path.

The block also checks the exact u64 retirement capacity and the physical-time
capacity: `avr_device_cpu_deadline(Infinity)` returns the rounded-up CPU-half
position of `UINT64_MAX-1`, rather than converting Infinity to an integer.
Strict comparison of the integer-cycle span against this half-position prevents
an early whole-block timestamp fault. Near either counter limit, individual
instructions preserve the exact successful prefix and fault location. CPU-cycle
endpoints must remain below2^52 so half-cycle comparisons are exact in f64.

An accepted block enters context active1 and clocks its full span before any
register effects. With no intervening observable boundary, it commits the ALU
effects, final PC/SREG and exact retirement total together. It then uses the
ordinary native retirement call for the last instruction and IRQ arbitration.
The context's execPc identifies the final instruction. A clock reset/fault
cancels effects; an unexpected WAIT fails closed. The existing instruction path
handles every rejected block and every suspended instruction.

`runUntilPs` establishes a bounded physical deadline, rebasing its exact uint64
wall timestamp for the f64 runner offset. `step`/`run` explicitly select an
unbounded span only with an internal source. With CLKI selected these methods,
manual `clock`/`interrupt` and `runBlock` are rejected; use bounded `runUntilPs`.
An unknown CLKI horizon returns normally with explicit `state().clki` status,
allowing another edge batch or finite periodic descriptor to resume the same
context. Instruction counts include completed retirements only.
`state().cpuPhase` exposes active,
word execPc, stage, remainingHalves and retired. It is diagnostic state, not a
second source of CPU truth. `capturePhysical` integrates pin levels inside
native WASM across exact sample deadlines. CLKI capture preflights the full
requested input horizon, including a known held level; insufficient input fails
before CPU/audio mutation. Legacy duty capture is unavailable in this optional
mode. No host callback is used for instruction/clock phases.

Package v5 records `resumable` and the initial CLKI profile, matches the
translation's `executionMode:'resumable-v1'`, and validates phase exports,
signatures, the 80-byte layout and nonoverlap with other ABI regions. It stores
an initial device image, not an active continuation or queued source signal.
Versions 1..4 retain their historical contracts and do not acquire this ABI.
The [CLKI contract](clki-design.md) describes PB3, divider/startup/sleep, known
holds, input horizons and the finite native producer. Its deterministic phase
policy and optional ideal validation do not establish measured silicon phase.

The generated control, local and memory encodings follow the official
[WASM binary instruction specification](https://webassembly.github.io/spec/core/binary/instructions.html);
the early exits follow its
[`return` execution rules](https://webassembly.github.io/spec/core/exec/instructions.html#exec-return).

## Verification

`node --test web-player/tests/attiny13a-cpu-phase-native.test.mjs` compiles the
real C CPU bridge and board using the read-only toolchain, warnings as errors
and no WASM imports. It checks the ABI, fractional spans, exact deadlines,
CLKPR, all three IRQ stages, wait/resume, SEI/RETI-delay preservation, reset
cancellation, real Flash-generation changes/SPM halt, SLEEP and disabled mode.

`avr-resumable-runtime.test.mjs` slices all123 official forms at every half edge
and adjacent1ps deadline, comparing final CPU/memory state with the existing
full-device path. It also checks public entry points, ABI/cache/mode identity,
package v5 roundtrips/ABI rejection, SLEEP/BOD recovery and audio partition
invariance.
`avr-resumable-oracles.test.mjs` records real native bridge calls in WASM to
check read latches, stack phases, once-only RFLB/EEPROM commands, reset/edge
ties and persistent IRQ entry across actual WAIT returns.

`attiny13a-resumable-blocks.test.mjs` proves that blocks actually execute and
compares them with the original generated instruction path, including exact
deadlines, half-cycle starts, IRQ/input/reset boundaries, protected windows,
CLKPR/OSCCAL, register/I/O aliases and both64-bit counter limits. The physical
timestamp regression first reproduced an early fault with zero retirements;
the guarded path now retains the same four successful instructions as stepping.
Native WASM phase probes also require `run` and `runUntil` to deliver one actual
14-cycle span for an eligible12-instruction block. The regressions first saw
individual one-cycle calls because the dispatch budget comparison used f64.gt
(`0x64`) instead of f64.lt (`0x63`). These checks prove block activation as well
as state parity; equal final state alone cannot establish that an optimization
ran. Probe calls remain entirely within WASM.

`attiny13a-clki-runtime.test.mjs` and
`attiny13a-clki-periodic-runtime.test.mjs` exercise the connected external source
and host producer. These are verification entry points, not a statement that
the latest combined integration run has completed.
