# Reuse a counter's sign bit to share filter output code

Measured exact IIR factoring for ATmega328P / classic AVR5, GNU AVR ABI,
AVR GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax -fwrapv
-fno-strict-aliasing`, avr8js 0.21.1. The selected recipe saves **212 B**
in complete WB images, adds **1000 cycles/frame**, and keeps the original
stack and state. Existing explicit C fallback and architecture/ASM-enable
selection are untouched. Xiph Speex 1.2.1 arithmetic/BSD provenance remains
in the source/vendor notices; the control-flow optimization is project work.

## Encode the phase in an already bounded counter

Each order-8/order-10 filter had separate warm and steady copies of rounding,
input addition, saturation, output storage, output negation and mirrored-history
updates. These operations can share one block per order. Coefficient-age
updates still belong only to warm outputs.

The existing T flag distinguishes the first `order-1` warm outputs from the
last warm output. Preserve that use: the second-last old coefficient is cached
until its new replacement must be forwarded for the final warm sample.

Use the sign bit of r3 for the separate warm/steady decision:

- Warm counters remain positive: `order-1` down to one, then a final counter
  of one after the existing CLT/SET transition.
- Steady groups start at `-order` and increment toward zero. Values stay
  negative until their final output is complete.

The common finish is entered only with a nonzero counter. Bit 7 therefore
identifies the phase without a new register, state flag or stack slot:

```asm
    ; Common rounding/output/negative-history body is above this point.
    sbrs r3,7
    rjmp .Lwarm_age
    inc r3
    breq .Lgroup_done
    rjmp .Lsteady_sample
.Lwarm_age:
    ; Preserve the original one-coefficient age update and forwarding.
    rjmp .Lwarm_finish_return
```

Warm code jumps into the same finish and returns to its original DEC/T-phase
continuation. Steady groups use INC rather than DEC. Both orders divide the
fixed forty-sample block, so the existing private history-revolution calls and
cursor resets remain valid. The source still rejects other orders. Do not
generalize this sign test to counters that can cross the signed8 midpoint.

All numerical instructions and their order are retained, including modulo-32
rounding overflow, signed24 input addition, clipping to +/-32767 and exact
negative output history. Input is read before output, preserving x==y. T,
cached coefficients, address updates and the last warm age transition retain
their original meaning. No new private call or return is introduced.

## Measured alternatives

| Isolated two-order recipe | Fixture Flash | Extra cycles/order-8 call | Extra cycles/order-10 call | Own ASM stack |
| --- | ---: | ---: | ---: | ---: |
| Original | 3696 B | 0 | 0 | 20 B |
| Local output helper per order | 3496 B | 280 | 280 | 22 B |
| One hidden COMDAT output helper | 3388 B | 280 | 280 | 22 B |
| Counter-sign shared finish | 3484 B | 120 | 130 | 20 B |

The phase recipe improves both size and speed over the local-helper recipe.
The COMDAT alternative shares the numerical prefix across both objects;
order-specific history/age stores remain at their callsites. Its private
register contract updates input/output pointers and returns the negative
clipped output, while preserving X, Y and the T phase. It is not a C ABI
entry. GNU ELF COMDAT discards the duplicate definition when both orders link.

In the complete layout, the COMDAT leaf's CALLs do not relax to short calls:
it saves 300 B raw / 298 B loaded, costing 2560 cycles/frame. The selected
phase recipe saves 212 B raw/loaded and costs 1000 cycles/frame, or 0.3125
CPU percentage point at 16 MHz / 50 frames per second. The additional 88 B
raw saving of the COMDAT variant costs another 1560 cycles/frame. Both remain
reproducible comparison recipes without a new production feature switch.

## Correctness, stack and loaded output

Every recipe passes 7374 isolated cases / 14748 C+ASM calls and 294960 samples
per path against the independent BigInt equations and original explicit C
filters. The cases include all 256 state low-address bytes, changing ages,
in-place/separate buffers, the full signed16 input/negation sweep, complete
work-arena guards and 7374 public ABI/r1 returns. Both C object files remain
byte-identical across recipes. Each per-case cycle difference is checked.

The phase IRQ proof passes **75999** instruction-boundary injections, including
**50471** interrupted nonzero-r1 states. All 32 registers, SREG including T,
PC and SP return intact; instruction traces match. Its private call/return
count stays 25809, own ASM stack 20 B and isolated IRQ peak 33 B. The shared
leaf passes 76103 injections as a separate measured alternative.

Complete image controls rebuild identically to the admitted `1da660ea`
baseline. Sources and generated profile cache are frozen independently of
parallel work. WB3.95 covers 18 streams capped at 64 frames (1152 frames);
WB12.8 covers one 64-frame long-recording prefix:

| Profile / recipe | Raw Flash | Mean cycles/frame | IRQ Flash | Minimum queue |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 baseline | 22940 B | 218603.772 | 23374 B | 30 |
| WB3.95 phase | 22728 B | 219603.772 | 23162 B | 30 |
| WB3.95 COMDAT leaf | 22640 B | 221163.772 | 23076 B | 30 |
| WB12.8 baseline | 22940 B | 233810.844 | 23374 B | 8 |
| WB12.8 phase | 22728 B | 234810.844 | 23162 B | 7 |
| WB12.8 COMDAT leaf | 22640 B | 236370.844 | 23076 B | 7 |

Raw PCM/reset and production s16/PWM remain exact. All loaded screens pass
with **8% extra foreground work and zero underruns**. Whole raw/IRQ stack
peaks remain 166/179 B for every recipe, with unchanged loaded free SRAM
444/422 B for these two profiles. Ready RAM screens do not measure transport
latency or physical hardware; broader five-profile admission is separate.

The selected source removes the now-unused IIR_FINISH macro definition and
keeps the shared finish body once. Two fixtures and four complete images
rebuild byte-identically after this source-only cleanup. The receipt binds
both source hashes and all six image identities; completed simulations were
not repeated for the cleanup.

## Reproduce

The [driver](../../Codecs/Speex/AVR/tests/screen_iir_output_size.py) preserves
all recipes and the cleanup. Supply the admitted pre-factoring codec root,
an existing prepared source cache, avr8js entry and retained screen corpus:

```sh
python Codecs/Speex/AVR/tests/screen_iir_output_size.py --source-root <baseline codec root> --avr-gcc avr-gcc --node node --profile-cache <profile/source> --avr8js-entry <avr8js/dist/cjs/index.js> --corpus <data/screen>
python Codecs/Speex/AVR/tests/screen_iir_output_size.py --phase audit --corpus <data/screen>
```

The [receipt](../../Codecs/Speex/AVR/reports/iir-output-size-screen.json) binds
LF-normalized sources, generated-cache digest, exact tools/header/avr8js/image/
C-object hashes and input/oracle hashes. Generated firmware, per-case timings
and logs stay under ignored `build/filter-size-next/`. Full project C decoders
are never executed or timed; the C runs above are isolated filter primitives.
