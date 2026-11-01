# Checked overflow in the host clock helper

Tested and rejected for the ATtiny13A verification runtime: freestanding
wasm32, C11, Clang 24 / Binaryen 133, Emscripten 6.0.12, original `-O3` build
flags. This concerns host execution speed and code size, not AVR firmware
arithmetic. It uses no assembly, WASM extension, new ABI or additional memory.

For uint64 inputs the helper computes `(a*b+carry)/d` with an exact remainder
and a potentially wide numerator. A failed call preserves both output values.
After the unchanged `d == 0` guard, its native-width admission is:

```c
if (!b || a <= (UINT64_MAX - carry) / b) {
    uint64_t n = a*b + carry;
    /* existing quotient/remainder path */
}
```

The candidate replaces only that admission:

```c
uint64_t n;
if (!__builtin_mul_overflow(a, b, &n) &&
    !__builtin_add_overflow(n, carry, &n)) {
    /* unchanged quotient/remainder path */
}
```

The [official Clang contract](https://clang.llvm.org/docs/LanguageExtensions.html#checked-arithmetic-builtins)
defines both operations for every input and reports whether the mathematical
result fits the destination type. Both checks succeed exactly when
`a*b+carry <= UINT64_MAX`: nonnegative carry cannot make an overflowing product
fit again. The zero-product case also succeeds. Otherwise the original wide
fallback receives the untouched input operands. Intermediate `n` is local;
failure must not publish it. Keep the zero-divisor guard and original output
write order. This equivalence is specific to these unsigned operands.

In the [measured experiment](../../web-player/reports/clock-intrinsic-20261101.md),
`ratio` loses one static `i64.div_u` (5 to 4), but the module grows ten bytes.
The existing compiler already leaves no `i64.rem_u` in either clock helper;
rewriting remainder as `n-q*d` would repeat its work. The
[WASM numeric semantics](https://webassembly.github.io/spec/core/exec/numerics.html)
specify results, not execution speed. Fewer static divisions need not improve
the executed paths or JIT register allocation.

All 5375 BigInt cases, focused clock tests and sixteen workload comparisons
pass. The four-case timing screen establishes no useful speedup; production
keeps the original guard. No benefit in working memory, real-time audio or
physical timing is claimed. The report retains exact inputs, compiler flags,
host versions, output hashes, timing controls and isolated rebuild commands.
Reconsider only with a new workload-based hypothesis, not instruction counts.
