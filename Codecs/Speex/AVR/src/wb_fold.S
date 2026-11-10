/* in-place 40 samples: t=floor(.9*x), v=low16((t*g+256)>>9),
 * alternating sign. Exact rounded HB1 excitation without a 32-bit buffer. */
#include "wb_fold_kernel.inc"
#include "zero_shape_kernel.inc"
.macro WB_FOLD_ARRAY name,count,parity,q15=1,skip_zero=0
.section .text.\name,"ax",@progbits
.global \name
.type \name,@function
\name:
    .irp reg,2,4,5,6,7,8,9,10,11,16
    push r\reg
    .endr
    movw r26,r24
    movw r4,r20
    movw r6,r22
    clr r2
    ldi r16,\count
.Lfold_\@:
.if \skip_zero
    /* Only the NB1 table entry uses this specialization: class2=0. */
    cpi r16,3
    brne .Lcalculate_\@
    st X+,r2
    st X+,r2
    rjmp .Lnext_\@
.Lcalculate_\@:
.endif
    ld r20,X+
    ld r21,X
    sbiw r26,1
.if \q15
    WB_FOLD_Q15 r8,r9,r10,r11
.endif
.if \parity
    WB_FOLD_SCALE r8,r9,r10,r11,r4,r5,r6,r7,r16
.else
    /* r2 stays zero: table entries have no output-position parity yet. */
    WB_FOLD_SCALE r8,r9,r10,r11,r4,r5,r6,r7,r2
.endif
    st X+,r9
    st X+,r10
.Lnext_\@:
    dec r16
    breq .Ldone_\@
    rjmp .Lfold_\@
.Ldone_\@:
    clr r1
    .irp reg,16,11,10,9,8,7,6,5,4,2
    pop r\reg
    .endr
    ret
.size \name,.-\name
.endm

WB_FOLD_ARRAY speex_wb_fold40_avr,40,1
#if SPEEX_ENABLE_NB1
WB_FOLD_ARRAY speex_wb_fold5_avr,5,0
/* Frame-invariant Q15 has already been cached, same second quantizer. */
WB_FOLD_ARRAY speex_wb_noise_scale5_avr,5,0,0,1
#endif

/* Fuse four ten-sample vectors with folding. ABI: out r24, indices r22,
 * scale r21:r18, g r17:r14. Indices 0..31, 0<=scale<=121000000;
 * g may be any signed32. No intermediate PCM loads/stores, same rounding.
 * All callee-saved registers and r1 restored, interrupts stay enabled. */

#if SPEEX_ENABLE_NB4 || SPEEX_ENABLE_NB2 || SPEEX_ENABLE_NB8
/* Private shared body, exact existing GNU argument ABI. Entry scratch:
 * X=table byte address, ZL=(width<<3)|vectors. Saved r14:r15 retain table,
 * r12 retains packed geometry; final low3 count bits terminate the loop. */
.macro WB_SHARED_ENTRY name,vectors,width,table
.section .text.\name,"ax",@progbits
.global \name
.type \name,@function
\name:
    ldi r26,lo8(\table)
    ldi r27,hi8(\table)
    ldi r30,(\width*8+\vectors)
    rjmp speex_wb_excitation_shared_avr
.size \name,.-\name
.endm
WB_SHARED_ENTRY speex_wb_excitation40_avr,4,10,exc_10_32_table
WB_SHARED_ENTRY speex_wb_excitation8_40_avr,5,8,exc_8_128_table
#if SPEEX_ENABLE_NB2
WB_SHARED_ENTRY speex_wb_excitation_nb2_40_avr,4,10,exc_10_16_table
#endif
#if SPEEX_ENABLE_NB8
WB_SHARED_ENTRY speex_wb_excitation_nb8_40_avr,2,20,exc_20_32_table
#endif
.section .text.speex_wb_excitation_shared_avr,"ax",@progbits
.global speex_wb_excitation_shared_avr
.type speex_wb_excitation_shared_avr,@function
speex_wb_excitation_shared_avr:
    .irp reg,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push r\reg
    .endr
    movw r28,r24
    movw r4,r18
    movw r6,r20
    movw r8,r14
    movw r10,r16
    movw r14,r26
    movw r26,r22
    mov r12,r30
    clr r2
    ldi r18,4
    mov r13,r18
.Lshared_vector:
    mov r21,r12
    lsr r21
    lsr r21
    lsr r21
    ld r20,X+
    mul r20,r21
    movw r30,r0
    add r30,r14
    adc r31,r15
    mov r3,r21
.Lshared_sample:
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
    breq .Lshared_next
    rjmp .Lshared_sample
.Lshared_next:
    dec r12
    mov r18,r12
    andi r18,7
    breq .Lshared_done
    rjmp .Lshared_vector
.Lshared_done:
    clr r1
    .irp reg,29,28,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2
    pop r\reg
    .endr
    ret
.size speex_wb_excitation_shared_avr,.-speex_wb_excitation_shared_avr

#else
#include "wb_excitation_kernel.inc"
WB_EXCITATION speex_wb_excitation40_avr,4,10,exc_10_32_table

/* Five eight-sample NB4 vectors, 5 indices 0..127; same scale/g domain. */
WB_EXCITATION speex_wb_excitation8_40_avr,5,8,exc_8_128_table

/* Low-rate codebooks share the exact same arithmetic and even-row parity.
 * Bias remains4 even for mode8's two vectors; see template geometry guard. */
#if SPEEX_ENABLE_NB2
WB_EXCITATION speex_wb_excitation_nb2_40_avr,4,10,exc_10_16_table
#endif
#if SPEEX_ENABLE_NB8
WB_EXCITATION speex_wb_excitation_nb8_40_avr,2,20,exc_20_32_table
#endif

#endif
