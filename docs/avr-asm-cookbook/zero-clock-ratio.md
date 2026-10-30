# Zero elapsed clock ratio: rejected experiment

Target: ATtiny13A full-device WASM, the current Clang/O3 freestanding uint64
clock helper. This concerns host execution cost; it changes no AVR instruction,
flag or virtual event. The original C implementation remains in production.

For `floor((a*b+carry)/divisor)`, after rejecting a zero divisor, the condition
`a == 0 && carry < divisor` proves quotient zero and unchanged remainder.
The tested insertion in `device_clock_ratio` was:

```c
if (!a && carry < divisor) {
    *quotient = 0;
    *remainder = carry;
    return 1;
}
```

Improper carries retain the original normalization path; invalid divisors retain
their original failure and unchanged-output behavior. No invalidation, event
service, CPU phase, wake, mirror/publication or host boundary is removed.
This is pure C arithmetic with no platform assembly or extra ISA requirement.

The candidate passed 225 new zero-product/carry combinations, all seven clock
tests, and 16 old/new workload comparisons. Only native function 155 (`ratio`)
changed, growing 522 to 539 bytes. The entire native grew 17 bytes; imports,
exports, CPU bytes/ABI and fixed memory stayed the same.

Performance did not justify retention. Four initial four-label screens were
inconclusive on music, despite a direct-kernel improvement in that capture.
A longer Rhythmic confirmation had median old/new 0.957x, favoring old in 6/8
pairs. Identical-binary variation remains substantial, so this is not proof of
a universal source-caused regression. It fails to establish useful speedup.
The remaining confirmation was stopped, and production was restored exactly.
Do not re-enable this branch based on source-entry counts or fewer divisions.

The [retained evidence](../../web-player/reports/clock-zero-20261030.md) includes
all completed timings, null controls, exact-output checks and reconstruction
text/hash for the candidate. The independent collector verifies restoration:

```text
node web-player/scripts/verify-clock-zero.mjs --input build/clock-zero-20261030 --output build/clock-zero-replay.json
```

The raw inputs must be retained locally; a replay does not rerun timing. For a
new experiment, use a task worktree, apply the insertion after divisor validation,
build the native runtime, then use `benchmark-runtime-controls.mjs` with
`--baseline-ref 702450d8 --change-set clock-zero`. Keep correctness, fresh four-label
warmups, active ADC/watchdog/CLKI controls and uninstrumented measurements.
Restore native/header/manifest before running this rejected-experiment collector.
No real-time or hardware coverage improvement follows from this attempt.
