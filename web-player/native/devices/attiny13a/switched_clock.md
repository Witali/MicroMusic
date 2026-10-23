# Constant-frequency switched clock

This module implements the selected logical source contract: a constant
frequency with on/off control. It maps wall picoseconds to elapsed source
half-periods in O(1), without a queue, generated edge stream or per-tick work.
It does not own PB3, a divider, peripheral domains, CPU execution or host APIs.

Initialization accepts an explicit time below uint64 MAX, frequency1..20MHz and
enabled0/1. Source half count and fractional phase start at0; the initial
abstract output is high. Public fields are read-only, with current output
`!(source_half &1)`. There is no runtime frequency-change operation.

When enabled, advancing by delta ps computes exactly:

```text
total = delta * (2*frequencyHz) + oldPhase
newSourceHalves = floor(total /1e12)
newPhase = total mod1e12
```

The shared `device_clock.h` integer helper handles products wider than uint64
without host imports. Its bounded arithmetic work is independent of elapsed
source periods. No absolute timestamp is multiplied by a frequency. Advancing
in arbitrary batches gives the same count/remainder as one uninterrupted span.

When disabled, advance changes wall time only. Source count, output and
fractional phase are frozen. `set_enabled` acts at the current stored time,
preserves that phase, and creates no synthetic edge. Advance to a switch time
first, then set its new state; repeated equal times or enabled values are valid.
After resumption, only the unelapsed fraction of the current half-period remains.
The physical freeze/resume phase is an explicit fixture choice, not a measured
silicon guarantee.

`deadline_halves` is read-only and returns the earliest absolute integer ps
at which the requested additional source half-periods have elapsed. It subtracts
the retained phase before upward rounding. Zero returns now even while off.
A nonzero request while off returns MAX. Invalid state, a count overflow, a
time overflow or an endpoint equal to reserved MAX also returns MAX. There is
no prediction of when an outside caller will enable the source again.

Init/advance/set_enabled return1 on success or a negative status. Argument,
time and arithmetic rejection is atomic and nonsticky. The board owner decides
how those errors affect emulation. Absolute source counts are monotonic and
time always remains authoritative; stopped wall intervals add no source count.

This is a logical constant-frequency fixture. It does not by itself establish
VCC-dependent electrical validity, slew, safe frequency transitions or silicon
phase. It intentionally implements the simpler fixed-frequency/on-off control;
no caller must provide a clock transition for every external tick.

Run `node --test web-player/tests/attiny13a-switched-clock.test.mjs`.
The standalone C/WASM tests check exact BigInt arithmetic, arbitrary batching,
mid-phase switching, huge stopped intervals, deadline boundaries and a small
explicit-front oracle used only in tests. The compiler checks for no host imports.
