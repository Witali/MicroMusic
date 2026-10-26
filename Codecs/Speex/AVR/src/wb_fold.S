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
#include "wb_excitation_kernel.inc"
WB_EXCITATION speex_wb_excitation40_avr,4,10,exc_10_32_table

/* Five eight-sample NB4 vectors, 5 indices 0..127; same scale/g domain. */
WB_EXCITATION speex_wb_excitation8_40_avr,5,8,exc_8_128_table
