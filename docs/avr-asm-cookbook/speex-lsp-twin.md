# One prologue, two polynomial passes

Classic AVR5 with hardware MUL, GNU ABI; measured with AVR GCC 7.3.0 at
`-Os -flto -mcall-prologues -mrelax`. Original project optimization; arithmetic
derives from Xiph Speex 1.2.1, whose BSD notices remain in the codec/vendor.

When two independent operations use the same callee-saved working registers,
save them once. Retain the second pointer/operand in preserved registers and
run a shared arithmetic body twice. A call-clobbered T bit can select private
return versus final epilogue without an extra phase register:

```asm
    ; Save working registers and retain the second arguments first.
    clt
    rcall .Lcore
    ; Load second arguments from their preserved register slots.
    set
    rjmp .Lcore
.Lcore:
    ; Arithmetic must not change T; clear r1 before either return.
    brts .Lrestore
    ret
.Lrestore:
    ; Restore callee-saved registers.
    ret
```

The [GNU AVR convention](https://avrdudes.github.io/avr-libc/avr-libc-user-manual-2.2.0/FAQ.html#faq_reg_usage)
permits T as scratch. It does not survive a general C call. Both passes must
preserve it internally, and IRQ handlers must restore interrupted SREG/T and
r1. The internal RCALL needs two stack bytes on ATmega328P. Do not assume the
same ABI or return-address size on other cores. Require disjoint p/q arrays;
keep each original rounded product and modulo-32 update intact.

The [Speex implementation](../../Codecs/Speex/AVR/src/lsp_pair.S) saves 16
register bytes once. Its shared source also emits the old single-stage ABI,
whose test image remains byte-identical. The [explicit C pair](../../Codecs/Speex/AVR/src/nb3_lsp_pair.h)
stays selectable on AVR, behind the same architecture plus separate ASM opt-in.
No hardware memory access or interrupt masking is introduced.

Pairs save 20 cycles including RET versus two single primitives. Whole NB8
improves 102,515.127 → 102,239.323 mean cycles (-0.2690%) for 78 extra Flash
bytes and four extra peak stack bytes; WB9.8 improves 0.2082% for 80 Flash
bytes, with unchanged observed whole-decoder stack. These are simulator/corpus
measurements, not general portability or board claims. Independent C/ASM/BigInt
checks and 30,870 IRQ injections include both T phases and internal RET.
All 134 fresh ASM PWM images pass with active interrupts and no underruns.
[Workloads, exact-output proofs and reproduction](../../Codecs/Speex/AVR/TWIN_LSP.md).

Unmeasured follow-up: place stage-2/3 entry blocks before stage 4 so its
shared descending tail falls through. Static instruction counting suggests
one extra stage-2 jump can replace two stage-4 jumps. Measure both NB and WB:
HB1 uses stages 2/3 without stage 4, so a local NB improvement can cost HB
time. This layout has not been assembled or admitted.
