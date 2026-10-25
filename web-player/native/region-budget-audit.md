# Adaptive instruction budget for register-only WASM regions

Scope: optional boundedRegions in the resumable ATtiny13A generated CPU.
Native peripherals, clocks, ABI and physical pin/audio queues are unchanged.
The original single-instruction path and boundedRegions=false remain explicit
correctness oracles. No new arithmetic instruction lowering or AVR assembly is
introduced. Other device profiles are not validated by this checkpoint.

## Admission proof

A region remains limited to the existing pure register/ALU instructions and
RJMP, conditional branches and register/bit skips. All memory/I/O, stack,
control operations and unsupported/external entries retain their original paths.
Per-node costs remain the documented whole AVR instruction cycles; maxCost is
1–3, including a skip over a two-word instruction. Every observable SREG exit
retains full flags. Cached GPR writes remain masked to bytes.

The previous region required all min(remainingInstructions,32) instructions at
their worst-case cost to fit before every deadline, or declined the region.
The revised generator uses the same strict admission bound but can reduce that
instruction budget. Define:

```
L = min(caller instruction count, 32)
C = maximum instruction cost in this region
T = min(earliest native event in CPU cycles,
        converted caller physical deadline, 2^52)
D = T - current CPU cycles
```

If currentCycles + L*C < T, retain L. Otherwise require T > currentCycles,
then use floor((ceil(D)-1)/C); decline if fewer than two instructions fit.
For integer cycle cost, ceil(D)-1 is the greatest integer strictly less than D.
The division truncates a nonnegative quantity. This branch is entered only
when 0 < D <= L*C <= 96; the float-to-i32 conversion cannot see an infinite,
negative or overflowing operand. Small integer dividends and C<=3 also keep
roundoff away from a truncation boundary. A private f64 local retains T after
the existing i32 locals and cached GPRs; it changes no memory/ABI field.

Native event distances are conservatively rounded down; caller physical bounds
are rounded up to half cycles. Whole-cycle region spans still compare strictly
below both. The 2^52 ceiling preserves exact half-cycle representation. The
tests include exact and adjacent 1ps endpoints; no epsilon is subtracted from
the physical scheduler or its timestamps. Keep the existing 9MHz endpoint-tie
regressions rather than inferring correctness from integer-frequency fixtures.

Pending IRQ, interrupt delay, active continuation, inactive CPU/reset/fault,
retirement headroom and the original public dispatch guards remain. Check
uint64 retirement capacity against the admitted L. CLKI exposes a zero native
budget and never enters a positive region; all supplied source edges remain
serviced. Internal/external-entry fallbacks and legacy packaged CPU code remain
valid. The ordinary generated CPU is byte-identical with boundedRegions=false.

## Commit and observation boundary

The loop executes at most L instructions with their path-dependent actual
costs, exiting on the original region boundary. One native phase-clock call
advances that actual span, seeing old GPRs/SREG. Only after successful completion
are cached GPRs, full SREG, next PC and retirement committed. A failed/partial
native barrier cannot publish speculative registers. Proven event-free bounds
prevent reset/IRQ/input events inside that span; subsequent ordinary barriers
still observe events exactly at their original scheduler times.

Smaller budgets are not permission to reduce peripheral clock accuracy, merge
across an unproved bus access or omit pin events. Native scheduler changes and
generator budget changes must be measured independently. Source-entry/call
removal and sampled inclusive percentages alone do not prove elapsed gains.

References:
[AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[WASM binary numeric instructions](https://webassembly.github.io/spec/core/binary/instructions.html#numeric-instructions),
[WASM numeric semantics](https://webassembly.github.io/spec/core/exec/numerics.html).
The new MVP operations are f64.min (0xa4), f64.ceil (0x9b), f64.div (0xa3) and
i32.trunc_f64_s (0xaa); the supported source range is part of the proof above.
See the measurement report for toolchain, workload, limitations and validation.
