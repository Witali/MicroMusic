# Optional floating-point synthesis

`LPX4_FLOAT_SYNTHESIS=1` selects genuine double synthesis in the existing
`Lpx4HybridCore`. The container, entropy parser, pulse packets and discrete
pitch-code reconstruction stay shared. This mode does not obtain floating
output by converting fixed PCM. The default is `0`, retaining fixed C/ASM
arithmetic and the existing object layout.

Select the flag identically for the core and every caller. Floating synthesis
requires `LPX4_ENABLE_ASM=0`, binary double precision of at least 53 significant
bits, and IEEE754 double. Unsupported values or assembly selection fail at
compile time. The ordinary AVR toolchain's 32-bit double is insufficient.
This is a desktop/larger-target option, not a small-AVR floating profile.

For the v9 reader, also select the existing speech/compact options:

```
-DLPX4_FLOAT_SYNTHESIS=1 -DLPX4_ENABLE_ASM=0
-DLPX4_ENABLE_SPEECH=1 -DLPX4_ENABLE_SPEECH_COMPACT=1
-DLPX4_COMPACT_ONLY=1 -DLPX4_COMPACT_VERSION=9
```

The same option also works with the existing v5/v8 build selections. No new
wire-format flag or recording metadata is introduced.

## Arithmetic and output

Quantized LSFs retain their serialized bin centers. Cosines, LSF-to-LPC
polynomials, LPC anchor interpolation, synthesis history, deemphasis history
and brightness calculations use double. There is no per-product floor or
intermediate integer-state rounding. The existing discrete pitch-code rules
and scale reconstruction table remain part of the recording format.

The P/Q factors are `(1 +/- z^-1)` followed by five
`(1 - 2*cos(omega)*z^-1 + z^-2)` factors each. Their half-sum supplies LPC
coefficients, bounded to the equivalent existing Q12 range
`[-32767/4096,32767/4096]`. Anchor locations and interpolation timing retain
the decoder's existing rules, including second-half endpoint reuse.

Codec range clamps remain: synthesis and deemphasis are bounded to
`[-32767,32767]` in the existing signal units; brightness input/output is
bounded to `[-16384,16384]`. Clamping limits range; it does not round history.
Both linear and mirrored histories retain double values. Floating polynomial
workspace is local double storage and does not reuse the discrete pitch ring.

`nextFloat(double&)` returns the postfilter signal divided by 16384, normalized
to `[-1,+1]`, without PCM quantization. Like other sample methods it returns
false on EOF/error, leaves its output argument unchanged on false, and uses
the existing error/progress accessors. Drain once after the declared sample
count to validate v9's final payload/padding.

Existing adapters remain available. They quantize only the returned sample:

- `nextS16`: nearest integer to `2*b`, clipped to `[-32768,32767]`.
- `nextQ14`: nearest integer to `b`, clipped to `[-16384,16384]`.
- `next`: the existing PWM gain/rounding selection applied to double `b`.

Nearest ties go toward positive infinity. With `LPX4_PWM_ROUND=0`, PWM truncates
the signed offset toward zero. Calling an integer/PWM adapter never converts
or overwrites double synthesis/filter state. See `C_REFERENCE.md` for the
batched floating output API and numeric-mode cache validation.

## Validation and limits

`tests/test_float_synthesis.py` needs g++ and Python's standard library. It
compares the DSP with an independent direct-convolution scalar-double model,
checks fractional histories/coefficients, both history layouts, Q4 choices,
anchor layouts, LPC segments 1/2/4, standard/SRAM512 settings, ROM/callback
input, source resets, partial tails and malformed EOF. It also compares all
final output adapters and verifies identical retained double state.

This numeric mode intentionally produces different samples from fixed-point
synthesis. Floating rounding can also differ slightly across compilers and
architectures. No claim of improved perceived quality or embedded real-time
support is made. The fixed decoder remains the bit-exact embedded reference.
