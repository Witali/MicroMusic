# Seed a MAC sum from its first product

Classic AVR5 / ATmega328P, hardware MUL/MOVW, GNU ABI; measured with AVR GCC
7.3.0, `-Os -flto -mcall-prologues -mrelax`. Original project adaptation of
the first-write rule already used by the pitch kernels. The remaining signed
MAC retains its AVR201 method-B carry chain; existing provenance is preserved.

For a nonempty dot product, initialize the sum with the first product.
On this signed16×signed16 modulo32 kernel, direct high/low partial-product
stores replace four accumulator clears and three accumulation instructions.
Both signed cross terms still execute with their original sign corrections.
This saves seven cycles per sample without a new call or runtime branch.
The compile-time GAS macro selects first-write versus later accumulation.

Two adjacent register copies can use MOVW when both register-pair bases are
even. Here `MOV r22,r24; MOV r23,r25` becomes `MOVW r22,r24`, saving one cycle
and one instruction without changing flags.

A two-byte negation can use:

```asm
com r23          ; high byte first: COM also changes C
neg r22          ; C = original low byte != 0
sbci r23,255     ; exact high-byte carry for -word
```

This saves one cycle against two COMs followed by a two-byte add-one sequence.
SBCI requires a high register; the flags after the entire sequence differ from
some longer variants. Check consumers before replacing it. In this filter,
the next cursor comparison establishes control-flow flags; IRQs preserve
interrupted SREG. C remains explicitly selectable on the same AVR.

The [assembled shared kernel](../../Codecs/Speex/AVR/src/iir_kernel.inc) emits
both order-8 and order-10 filters. Production C is in
[iir_direct.c.inc](../../Codecs/Speex/AVR/src/iir_direct.c.inc) and
[wb_iir.c](../../Codecs/Speex/AVR/src/wb_iir.c). Their arithmetic, state,
coefficient ageing, clipping, aliases and backend-selection contract are unchanged.

Together the three changes save **360 cycles / 40-sample block**, 1,440 per
NB frame and 2,880 per WB frame. NB8 mean improves 1.4527%, Flash -36 B;
WB12.8 improves 1.1710%, Flash -72 B. Static SRAM and whole-decoder stack are
unchanged. Measurements cover 47,735 exact decoder/reset frames; these do not
establish board timing or an optimum for every architecture.

Direct tests compare selected/explicit production C with BigInt on both
orders, all state low bytes and every signed16 input through a zero-coefficient
filter. Separate transposed-reference tests cover 983,040 samples. Eight full
ASM traces receive 76,667 instruction-boundary IRQs with all registers/flags
restored. [Bounds, admission and reproduction](../../Codecs/Speex/AVR/IIR_SEED.md).

All 198 fresh production ASM PWM images pass active timers/IRQs with zero
underruns, including NB +40% and both WB voice corpora +8% foreground work.
Two RAM-input images also pass 10,563 full-history frames per WB mode +8%.
These results assume the tested output ISR; extra work is not an arbitrary
ISR load or physical-board guarantee. Input transport is not modeled.
