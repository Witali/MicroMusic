# Evaluate wake delays only when requested: rejected experiment

Target: ATtiny13A's full internal-clock model, freestanding wasm32, original
C11/O3 Clang 24 and Binaryen 133 build through registered Emscripten 6.0.12.
This concerns host execution cost, not AVR firmware assembly. Production remains
unchanged; the candidate is reconstructed only under ignored `build/`.

The [manufacturer data sheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 4.7.1 and 7.1/Table 7-1, distinguishes sleeping from actual wakeup and
adds four CPU cycles to a wake response. The experiment keeps those cycles,
the selected startup policy and every peripheral/CLK/IRQ event. It changes only
evaluation of unused delay values while the pending-source mask is zero.

The original `wake` still computes recovery and configured startup before its
fixed source delays. The candidate keeps those first computations, including
possible startup overflow, but computes the fixed 12-source-half startup bound
and 8-divided-source-half wake hold only when `pending != 0`:

```c
uint64_t extra = 0;
if (pending) {
    /* original fixed source startup selection */
    extra = source_duration(8u * board.divisor);
}
/* original recovery maximum, then the same exact wake policy */
```

Why the omitted computations cannot fault for admitted internal-clock state:
their units are at most 2048, base frequency at most 1e12, source rate at least
two, and phase zero. Their products and rounded quotients fit uint64. These
are software configuration bounds, not silicon operating-frequency claims.
The configured arbitrary startup does not have the same proof and must retain
its original validation even with no wake source. Dropping that validation
would silently suppress an existing failure.

Still call `system_sleep_wake_exact`: its no-source path advances `sleep.now`.
Skipping the entire wake/service call would change that cursor. A nonzero mask
whose source cannot wake the selected mode follows the original path. CLKI
returns through its separate actual-edge policy before this candidate.

Six retained tests check both versions, including 144 empty-poll combinations,
96 first-wake combinations after frequency/divider changes, BOD recovery,
backwards cursors, non-waking requests and overflow at the uint64 horizon.
They use manufacturer-derived bit/vector constants and independent integer
rounding expectations. The cases are digital fixtures, not internal-phase or
silicon measurements.

The [measured experiment](../../web-player/reports/empty-wake-20261101.md)
preserves all sixteen workload comparisons and 5259 exact checkpoints. Two
balanced timing series do not establish a sufficient benefit over identity
variation. The prototype is not retained. A smaller binary or fewer source
entries alone does not overturn that decision; do not repeat this guard from
counts alone. Reusable isolated-builder, policy-selection and regression checks
remain available. No speed, working-memory, real-time audio or hardware-fidelity
improvement is claimed.
