/* in-place 40 samples: t=floor(.9*x), v=low16((t*g+256)>>9),
 * alternating sign. Exact rounded HB1 excitation without a 32-bit buffer. */
#include "wb_fold_kernel.inc"
#include "zero_shape_kernel.inc"
.section .text.speex_wb_fold40_avr,"ax",@progbits
.global speex_wb_fold40_avr
.type speex_wb_fold40_avr,@function
speex_wb_fold40_avr:
    .irp reg,2,4,5,6,7,8,9,10,11,16
    push r\reg
    .endr
    movw r26,r24
    movw r4,r20
    movw r6,r22
    clr r2
    ldi r16,40
.Lfold:
    ld r20,X+
    ld r21,X
    sbiw r26,1
    WB_FOLD_Q15 r8,r9,r10,r11
    WB_FOLD_SCALE r8,r9,r10,r11,r4,r5,r6,r7,r16
    st X+,r9
    st X+,r10
    dec r16
    breq .Ldone
    rjmp .Lfold
.Ldone:
    clr r1
    .irp reg,16,11,10,9,8,7,6,5,4,2
    pop r\reg
    .endr
    ret
.size speex_wb_fold40_avr,.-speex_wb_fold40_avr

/* Fuse four ten-sample vectors with folding. ABI: out r24, indices r22,
 * scale r21:r18, g r17:r14. Indices 0..31, 0<=scale<=121000000;
 * g may be any signed32. No intermediate PCM loads/stores, same rounding.
 * All callee-saved registers and r1 restored, interrupts stay enabled. */
.section .text.speex_wb_excitation40_avr,"ax",@progbits
.global speex_wb_excitation40_avr
.type speex_wb_excitation40_avr,@function
speex_wb_excitation40_avr:
    .irp reg,2,3,4,5,6,7,8,9,10,11,12,13,16,17,28,29
    push r\reg
    .endr
    movw r28,r24
    movw r26,r22
    movw r4,r18
    movw r6,r20
    movw r8,r14
    movw r10,r16
    clr r2
    ldi r18,4
    mov r12,r18
    mov r13,r18
.Lfused_vector:
    ld r20,X+
    ldi r21,10
    mul r20,r21
    movw r30,r0
    subi r30,lo8(-(exc_10_32_table))
    sbci r31,hi8(-(exc_10_32_table))
    ldi r18,10
    mov r3,r18
.Lfused_sample:
    movw r16,r4
    movw r18,r6

    SPEEX_ZERO_SHAPE r13
    mov r20,r23
    mov r21,r24
    WB_FOLD_Q15 r22,r23,r24,r25
    WB_FOLD_SCALE r22,r23,r24,r25,r8,r9,r10,r11,r3
    st Y+,r23
    st Y+,r24
    dec r3
    breq .Lfused_next
    rjmp .Lfused_sample
.Lfused_next:
    dec r12
    breq .Lfused_done
    rjmp .Lfused_vector
.Lfused_done:
    clr r1
    .irp reg,29,28,17,16,13,12,11,10,9,8,7,6,5,4,3,2
    pop r\reg
    .endr
    ret
.size speex_wb_excitation40_avr,.-speex_wb_excitation40_avr
