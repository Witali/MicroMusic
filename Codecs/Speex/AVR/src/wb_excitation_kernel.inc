/* Shared exact NB innovation -> HB1 fold. GNU ABI and clobbers are in
 * wb_fold.S. Vector count and rounding bias4 are deliberately separate. */
.macro WB_EXCITATION name,vectors,width,table
.if (\vectors*\width != 40) || (\width & 1)
    .error "WB excitation needs forty samples in even-width vectors"
.endif
.section .text.\name,"ax",@progbits
.global \name
.type \name,@function
\name:
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
    ldi r18,\vectors
    mov r12,r18
.if \vectors != 4
    ldi r18,4
.endif
    mov r13,r18
.Lfused_\@_vector:
    ld r20,X+
    ldi r21,\width
    mul r20,r21
    movw r30,r0
    subi r30,lo8(-(\table))
    sbci r31,hi8(-(\table))
    ldi r18,\width
    mov r3,r18
.Lfused_\@_sample:
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
    breq .Lfused_\@_next
    rjmp .Lfused_\@_sample
.Lfused_\@_next:
    dec r12
    breq .Lfused_\@_done
    rjmp .Lfused_\@_vector
.Lfused_\@_done:
    clr r1
    .irp reg,29,28,17,16,13,12,11,10,9,8,7,6,5,4,3,2
    pop r\reg
    .endr
    ret
.size \name,.-\name
.endm
