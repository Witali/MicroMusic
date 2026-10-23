# Native ATtiny13A CPU continuation contract

This is an optional physical-time execution backend. It does not decode guest
opcodes or change the legacy executor. The translated emitter owns instruction
effects, PC/SREG commits and its saved locals/stage. Native code supplies bounded
clock spans, asynchronous reset cancellation and resumable interrupt entry.
There is no external CLKI edge source integration in this change.

## Stable context and exports

Call `avr_device_phase_enable(1)` before the first `avr_reset`. It returns1 for
pre-init values0/1 and0 for an invalid value or a late configuration. Enabling
requires the existing physical1ps board profile; a fixed oscillator legacy
timebase is rejected on reset. The enabled choice survives a subsequent cold
reset; the context, retirement counter and deadline are cleared by that reset.

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
clock phase through a partial period and prevents rounding a bus effect early.

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

## Verification

`node --test web-player/tests/attiny13a-cpu-phase-native.test.mjs` compiles the
real C CPU bridge and board using the read-only toolchain, warnings as errors
and no WASM imports. It checks the ABI, fractional spans, exact deadlines,
CLKPR, all three IRQ stages, wait/resume, SEI/RETI-delay preservation, reset
cancellation, real Flash-generation changes/SPM halt, SLEEP and disabled mode.
