/* Normalized 16-tap Q7 QMF. Signed16 half-sums/differences times signed8
 * coefficients, exact signed24 accumulation: 236*32768+32 < 2^23.
 * Same equation as wb_qmf.c; clamp once after rounded Q6 shift.
 * ABI: low r24, high r22, out r20, 64-byte state r18; fixed 40 pairs.
 * All callee-saved registers and r1 restored; interrupts remain enabled. */
.text

.macro WB_MAC a,b,c,d,coefficient
    ld r21,-X
    ld r20,-X
    ldi r18,lo8(\coefficient)
    muls r18,r21
    add \b,r0
    adc \c,r1
    mulsu r18,r20
    sbc \c,r2
    add \a,r0
    adc \b,r1
    adc \c,r2
.endm
.macro WB_FINISH a,b,c
    ldi r18,32
    add \a,r18
    adc \b,r2
    adc \c,r2
    mov r22,\c
    lsl r22
    sbc r22,r22
    .rept 2
    lsl \a
    rol \b
    rol \c
    rol r22
    .endr
    mov r20,\b
    mov r21,\c
    tst r22
    brmi .Lnegative\@
    brne .Lclippos\@
    sbrs r21,7
    rjmp .Lstore\@
.Lclippos\@:
    ldi r20,255
    ldi r21,127
    rjmp .Lstore\@
.Lnegative\@:
    cpi r22,255
    brne .Lclipneg\@
    sbrs r21,7
    rjmp .Lclipneg\@
    cpi r21,128
    brne .Lstore\@
    tst r20
    brne .Lstore\@
.Lclipneg\@:
    ldi r20,1
    ldi r21,128
.Lstore\@:
    movw r30,r8
    st Z+,r20
    st Z+,r21
    movw r8,r30
.endm
.global speex_wb_qmf40_avr
.type speex_wb_qmf40_avr,@function
speex_wb_qmf40_avr:
    .irp reg,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push r\reg
    .endr
    movw r4,r24
    movw r6,r22
    movw r8,r20
    movw r28,r18
    mov r25,r18
    subi r25,-32
    clr r2
    ldi r24,40
    mov r3,r24
.Lsample:
    movw r30,r4
    ld r18,Z+
    ld r19,Z+
    movw r4,r30
    movw r30,r6
    ld r20,Z+
    ld r21,Z+
    movw r6,r30
    mov r22,r19
    lsl r22
    sbc r22,r22
    mov r23,r21
    lsl r23
    sbc r23,r23
    movw r10,r18
    mov r12,r22
    sub r10,r20
    sbc r11,r21
    sbc r12,r23
    add r18,r20
    adc r19,r21
    adc r22,r23
    asr r12
    ror r11
    ror r10
    asr r22
    ror r19
    ror r18
    st Y,r10
    std Y+1,r11
    std Y+2,r18
    std Y+3,r19
    std Y+32,r10
    std Y+33,r11
    std Y+34,r18
    std Y+35,r19
    adiw r28,4
    movw r26,r28
    adiw r26,32
    cp r28,r25
    brne .Lcursor
    sbiw r28,32
.Lcursor:
    .irp reg,10,11,12,13,14,15,16,17
    clr r\reg
    .endr
    WB_MAC r14,r15,r16,r17,-10
    WB_MAC r10,r11,r12,r13,-4
    WB_MAC r14,r15,r16,r17,15
    WB_MAC r10,r11,r12,r13,7
    WB_MAC r14,r15,r16,r17,-26
    WB_MAC r10,r11,r12,r13,-14
    WB_MAC r14,r15,r16,r17,123
    WB_MAC r10,r11,r12,r13,37
    WB_MAC r14,r15,r16,r17,37
    WB_MAC r10,r11,r12,r13,123
    WB_MAC r14,r15,r16,r17,-14
    WB_MAC r10,r11,r12,r13,-26
    WB_MAC r14,r15,r16,r17,7
    WB_MAC r10,r11,r12,r13,15
    WB_MAC r14,r15,r16,r17,-4
    WB_MAC r10,r11,r12,r13,-10
    WB_FINISH r10,r11,r12
    WB_FINISH r14,r15,r16
    dec r3
    breq .Ldone
    rjmp .Lsample
.Ldone:
    clr r1
    .irp reg,29,28,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2
    pop r\reg
    .endr
    ret
.size speex_wb_qmf40_avr,.-speex_wb_qmf40_avr
