# Common binary factors in wide clock arithmetic

Target: the ATtiny13A verification runtime compiled for wasm32 with the pinned
Clang 24 / Binaryen 133 SDK, C11 and `-O3`. This concerns host execution of the
digital model, not arithmetic performed by a physical AVR or its firmware.
It requires only ordinary WASM integer operations; no ISA extension, assembly
backend, new device state or ABI is introduced.

The clock helper computes the quotient and numerator remainder of
`(a*b+carry)/d`, with unsigned 64-bit inputs and a potentially 128-bit product.
The quotient must fit uint64. Failed calls must preserve both output values.
Clock-delay conversion also preserves its earlier intermediate-overflow check
before subtracting phase. Keep these contracts when changing the arithmetic.

After the original native-width fast path fails, let:

```text
s = ctz(b | d), g = 2^s
b = g*b', d = g*d', carry = g*cHi + cLo

a*b+carry = g*(a*b'+cHi) + cLo
a*b'+cHi = q*d' + r'

quotient = q
remainder = g*r' + cLo < g*d' = d
```

Thus the existing decomposition/wide division can use the reduced operands.
Restoring the low carry bits gives the exact original remainder, including
improper carries greater than the original divisor. The quotient and its
overflow admission are unchanged. Remainder reconstruction cannot overflow.

The zero-divisor check precedes the reduction. Consequently `b|d` is nonzero
and the C builtin `__builtin_ctzll` is defined. Shifts 0 through 63 are valid
with an unsigned 64-bit constant. A zero multiplier already returns through the
original short path. Rescale outputs only after success, keeping their original
write order. Preserve the original implementation and independent BigInt
oracles while evaluating a candidate.

Why investigate this path: instruction-counted `run()` passes an infinite host
deadline to the resumable block guard. The bridge converts the finite physical
timeline limit `UINT64_MAX-1`, so some calls require a wide intermediate even
though the current instruction span is short. The existing capacity check must
remain. A writable public deadline shadow is insufficient grounds to remove it.
This is separate from the rejected equal-rate, bounded-multiplier and native
phase-subtraction experiments.

The [official WASM numeric semantics](https://webassembly.github.io/spec/core/exec/numerics.html)
define integer division, remainder and bit operations; their
[binary encoding](https://webassembly.github.io/spec/core/binary/instructions.html)
does not itself guarantee a particular native instruction sequence or speed.
Inspect the optimized artifact and measure identical workloads with balanced
identity controls. Source-PC containment and instruction counts alone are not
execution-time evidence. Preserve exact CPU/state/PCM/pin output, clock residues,
overflow failures and event ordering; the verification model's 10 ns timestamp
tolerance does not authorize changing these integer results.

The [retained experiment](../../web-player/reports/clock-power2-20261030.md)
passes 2642 checks and repeats a 1.169x/1.232x gain on the 20 MHz unbounded direct
kernel (16/16 positive pairs). It adds 109 WASM bytes; fixed memory and ABI stay
unchanged. Music/capture gains are unproven and small losses remain possible.
This is a measured, scoped runtime improvement, with no real-time audio,
working-memory, silicon calibration or new hardware-coverage claim.
