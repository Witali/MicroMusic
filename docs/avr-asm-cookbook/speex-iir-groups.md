# Cache coefficients according to their last use

Classic AVR5 / ATmega328P, hardware MUL/MOVW, GNU ABI, AVR GCC 7.3.0;
measured with `-Os -flto -mcall-prologues -mrelax`. Original project technique;
existing Speex/AVR201 provenance stays with the sources. Explicit C remains
selectable on AVR; unsupported or non-enabled ASM defaults to C.

When a circular-history loop has a fixed multiple of its length, process one
whole group before resetting its cursor. A private subroutine shares the
large arithmetic body without checking wrap on each output:

```asm
    .rept 40/IIR_ORDER-1
    rcall .Liir_group
    .endr
    ; External epilogue clears r1 and restores the saved registers.
.Liir_group:
    ; Count exactly IIR_ORDER outputs through the shared body.
    ; Then rewind Y once and return to the private assembly caller.
```

Immediate rounding biases free the old constant register for the count.
The obsolete cursor-limit/count pair holds a fourth coefficient instead.
MULSU can read r16:r17 directly, avoiding a scratch MOVW; operands in lower
registers still need copies into its supported r16..23 range.

Reuse that high pair differently during warm-up: the last **old** coefficient
changes only after the last warm output. Preload it from ages, not new `den`,
and use it on every warm sample. After warm-up the same pair receives the
first new coefficient. This is exact across changing coefficients and full
signed16 data, with no additional stored state.

The [shared assembled kernel](../../Codecs/Speex/AVR/src/iir_kernel.inc) saves
247 cycles/order-10 block and 238/order-8 block. Separate prototypes measure
the cursor hoist, grouped loops, fourth cache, direct operands and old-tail
cache. The latter alone saves another 36/28 cycles without increasing size.
The private RCALL costs two stack bytes on this target. r1 may stay dirty
across private RET, with no C call; clear it at the external ABI boundary and
require IRQ restoration of interrupted r1/SREG. Other return-address widths
and ABIs need their own measurements.

Full NB8 improves 1.0278%, WB12.8 0.8117%, including a separate exact
three-instruction cosine negate. Flash falls 4/6 B, static SRAM is unchanged;
whole WB stack grows two bytes. Direct C/ASM/BigInt and transposed tests pass,
including 75,479 IIR IRQ boundaries and dirty-r1 private returns.
[Workloads, PCM/PWM admission and reproduction](../../Codecs/Speex/AVR/IIR_GROUPS.md).

Final sources pass 198 production PWM images with active interrupts and zero
underruns. Both WB modes also pass 10,563 full-history frames each through
the production ISR/queue with ready RAM packets and 8% extra foreground work:
minimum queues 6/5, free SRAM 437/429 B. This is simulator evidence; transport
latency and physical hardware were not measured.

Untested follow-up: reset warm Y with a fixed subtraction instead of retaining
its base, freeing r12:r13 for the second-last old age. Run `order-1` warm
outputs with it, then forward the just-written new coefficient from r18:r19
into that pair for the final warm output. A T-bit phase flag could share the
body without another CALL; initialize it explicitly and preserve it in IRQs.
Static counting suggests 18/12 extra cycles per block, but this has not been
assembled, validated or admitted. Verify ageing, flags, all addresses and
active-IRQ timing before using it.
