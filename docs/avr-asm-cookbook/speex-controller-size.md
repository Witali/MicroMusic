# Bound controller size and retain exact interpolation

Measured on ATmega328P / AVR5, GNU AVR ABI, AVR GCC 7.3.0 with LTO,
mcall-prologues/mrelax, and avr8js 0.21.1. Original project control/compiler
experiments on `1da660ea`; Xiph Speex 1.2.1 arithmetic/BSD provenance remains
in the source/vendor notices. Explicit architecture/ASM selection and the
portable C backend remain intact.

## Choose attributes at the actual generated function

`nb_decode.c.inc` is pasted into generated `nb_celp.c`. Editing a fragment after
generation can create a false no-op experiment. Hash the generated function
and check the resulting symbol/image. Capture actual compiler policy with
`avr-gcc -mmcu=atmega328p -Q -O2 --help=optimizers` and the corresponding O3
command; flag differences apply only to that compiler version.

For the ASM-selected NB controller, retain noinline and use O2 instead of O3,
allowing LTO specialization. On the frozen graph the complete image changes
22940 -> 22070 B for +304.253 mean cycles across 249 WB9.8 frames.
Adding noclone here costs another 142 B and increases time. The output-ready
WB stage uses Os with its existing noinline/noclone boundary. Both C-backend
policies remain unchanged; generic/unsupported-target macros retain C defaults.

A thirteen-recipe search checked duplication, inlining and scalar passes.
Three extra O2 scalar passes save only 2..4 cycles/frame at unchanged bytes,
so production keeps plain O2. Seven aliases produce identical firmware;
1590 unique raw ASM frames cover six WB9.8 images and two WB7.75 controls.
The [receipt](../../Codecs/Speex/AVR/reports/compiler-policy-size-screen.json)
preserves all alternatives and their narrow observation scope.

## Encode proven repair positions in a small mask

Replace six expanded WB LSP margin checks by one loop. Two bits per position
in `0x0f9f` select the existing lower/upper repairs: 3,3,1,2,3,3 for positions
1..6. Keep forward mutation order, endpoint constraints and the two separate
arithmetic half-shifts in the upper repair; combining shifts changes rounding.
The table-derived endpoint domain proves which checks can be omitted. Do not
apply the mask to arbitrary unbounded LSP values.

The extracted current AVR function occupies 296 B versus 478 B unrolled;
mean isolated time changes 363.31 -> 465.31 cycles. Actual old/current bodies
and the separately rounded Xiph model match on **67108864 quarter cases**
(4096 possible old endpoints x 4096 new x four subframes), with output guards.
The refreshed HB response proof also matches **25171968** untouched Xiph
conversions and preserves the signed16 divisor/prefix bounds.

Together the three controller source changes save **1348 B** in the frozen
whole image (22940 -> 21592), at +1041.040 mean cycles on the 249-frame screen.
Current macro/comment formatting rebuilt to that exact observed binary.
This is a component screen; the full combined IRQ admission is separate.

[Controller/AVR receipt](../../Codecs/Speex/AVR/reports/wb-controller-size-screen.json),
[actual-body proof](../../Codecs/Speex/AVR/reports/wb-interpolation-mask-domain.json)
and [response proof](../../Codecs/Speex/AVR/reports/wb-size2-response-domain.json)
bind sources and oracles. Reproduce the scalar domain with
`tests/prove_wb_interpolation_body.py --cc gcc`; optional `--baseline-file`
must match the admitted baseline hash. Use `tests/check_wb_response.py` for
the paired response proof. Only extracted scalar C executes, never a complete
project C decoder. Historical compiler/AVR fixtures stay under ignored
`build/compiler-policy-extra/` and `build/controller-size/`.
