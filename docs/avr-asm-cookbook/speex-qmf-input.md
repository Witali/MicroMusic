# Exact QMF input arithmetic and first-tap initialization

Original project techniques, measured on classic AVR5 / ATmega328P with
hardware MUL, GNU AVR ABI, AVR GCC 7.3.0 and avr8js 0.21.1. They concern
speed and Flash size, not a change in synthesis quality. No other CPU timing
is implied. Xiph algorithm/coefficient provenance remains in the codec files
and `Codecs/Speex/AVR/vendor/speex-1.2.1/COPYING`.

## Signed averages through unsigned carry

For signed16 inputs `a,b`, let `A=a+32768`, `B=b+32768` (toggle bit 15):

```text
floor((a-b)/2) = floor((A-B)/2)
floor((a+b)/2) = floor((A+B)/2) - 32768
```

The unsigned SUB borrow is bit 16 of the signed17 difference. The unsigned
ADD carry is bit 16 of the unsigned17 sum. Feed that flag straight into ROR
of the high then low byte, avoiding explicit signed24 temporaries. Negative
odd differences retain floor rounding. No flag-changing instruction may
intervene between the arithmetic and the first ROR.

```asm
; a=r5:r4, b=r8:r7, bias r20=128; all original inputs already loaded.
eor r5,r20
eor r8,r20
movw r10,r4
sub r10,r7
sbc r11,r8
ror r11
ror r10             ; signed floor((a-b)/2)
add r4,r7
adc r5,r8
ror r5
ror r4
eor r5,r20          ; signed floor((a+b)/2)
```

This clobbers the input registers. Adjacent inputs can share the bias register
until the MAC reuses it. Preserve the old history record before either insert;
load both inputs before output stores when `high == out+40` is permitted.

## Initialize accumulators with the first product

Replace a zeroing pass plus the first MAC's adds with moves of that product.
Use MOVW only for an aligned destination pair. Consume saved values in their
last-use order so an intermediate copy is unnecessary.

Carry is part of the arithmetic contract: when initializing a signed24
accumulator, `MOV low,r0` does **not** clear the carry left by sign correction.
The middle-byte operation must be `ADD`, not the `ADC` needed by later taps.
An early prototype's stale carry was caught by the negative rounding-boundary
test; retain those cases. Do not initialize by changing the filter's rounding.

The [production ASM](../../Codecs/Speex/AVR/src/wb_qmf.S) implements both
techniques without per-tap calls. The [C fallback](../../Codecs/Speex/AVR/src/wb_qmf.c)
and backend selection remain unchanged. Standard compiled AVR ISRs preserve
SREG and interrupted nonzero r1; the external ASM return still clears r1 and
restores all callee-saved registers.

## Measured result and validation

With existing mixed function options, `-Os -flto -mcall-prologues -mrelax`,
one 40-pair QMF invocation saves **640 cycles**; a WB frame saves **2560**.
Both complete WB images shrink **64 B**, with unchanged static SRAM and stack.
Direct tests cover 2244 blocks / 179520 output words, all signed16 input
values, 92 clipping/rounding boundary blocks, alias/non-alias, exact mirrored
history, guards and ABI. Whole-decoder and active-IRQ evidence is retained
with the [codec report](../../Codecs/Speex/AVR/WB_QMF.md).

This is exact relative to the existing compact Q7/16-tap profile. It does
not turn that profile into full 64-tap Xiph synthesis. Real-time admission
must use the complete player with interrupts active, not the isolated kernel.

For later filter extensions, check the arithmetic **and** geometry: a block
length must divide the ring length if the cursor is implicitly zero per call;
mirroring also changes the maximum LDD/STD displacement. The
[offline screen](../../Codecs/Speex/AVR/WB_QMF_BUDGET.md) records the exact
24-tap cursor and 32-tap displacement constraints; those candidates are not
assembled or admitted.
