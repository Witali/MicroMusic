/* Normalized 16-tap Q7 QMF, two input pairs per iteration.
 * Same exact signed24 arithmetic as wb_qmf.c: 236*32768+32 < 2^23.
 * Shared history loads feed four accumulators; no additional state.
 * ABI: low r24, high r22, out r20, 64-byte state r18; fixed 40 pairs.
 * E0 r4..6, O0 r7..9, E1 r10..12, O1 r13..15; low r16:17,
 * high r18:19, out r22:23, zero r2, count r3, cursor end r25.
 * Loading both input pairs before four output stores preserves high=out+40.
 * All callee-saved registers and r1 restored; interrupts remain enabled. */
.text

/* The loaded signed16 value r24:r21 is reused for adjacent output pairs. */
.macro WB_LOAD
    ld r24,-X
    ld r21,-X
.endm
.macro WB_MAC a,b,c,coefficient
    ldi r20,lo8(\coefficient)
    muls r20,r24
    add \b,r0
    adc \c,r1
    mulsu r20,r21
    sbc \c,r2
    add \a,r0
    adc \b,r1
    adc \c,r2
.endm
.macro WB_INPUT
    movw r30,r16
    ld r4,Z+
    ld r5,Z+
    movw r16,r30
    movw r30,r18
    ld r7,Z+
    ld r8,Z+
    movw r18,r30
    mov r6,r5
    lsl r6
    sbc r6,r6
    mov r9,r8
    lsl r9
    sbc r9,r9
    movw r10,r4
    mov r12,r6
    sub r10,r7
    sbc r11,r8
    sbc r12,r9
    add r4,r7
    adc r5,r8
    adc r6,r9
    asr r12
    ror r11
    ror r10
    asr r6
    ror r5
    ror r4
    st Y,r10
    std Y+1,r11
    std Y+2,r4
    std Y+3,r5
    std Y+32,r10
    std Y+33,r11
    std Y+34,r4
    std Y+35,r5
    adiw r28,4
.endm
.macro WB_FINISH a,b,c
    ldi r20,32
    add \a,r20
    adc \b,r2
    adc \c,r2
    mov r0,\c
    lsl r0
    sbc r0,r0
    .rept 2
    lsl \a
    rol \b
    rol \c
    rol r0
    .endr
    mov r21,\b
    mov r24,\c
    tst r0
    brmi .Lnegative\@
    brne .Lclippos\@
    sbrs r24,7
    rjmp .Lstore\@
.Lclippos\@:
    ldi r21,255
    ldi r24,127
    rjmp .Lstore\@
.Lnegative\@:
    mov r20,r0
    cpi r20,255
    brne .Lclipneg\@
    sbrs r24,7
    rjmp .Lclipneg\@
    cpi r24,128
    brne .Lstore\@
    tst r21
    brne .Lstore\@
.Lclipneg\@:
    ldi r21,1
    ldi r24,128
.Lstore\@:
    st Z+,r21
    st Z+,r24
.endm
.global speex_wb_qmf40_avr
.type speex_wb_qmf40_avr,@function
speex_wb_qmf40_avr:
    .irp reg,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push r\reg
    .endr
    movw r16,r24
    movw r28,r18
    mov r25,r18
    subi r25,-32
    movw r18,r22
    movw r22,r20
    clr r2
    ldi r24,20
    mov r3,r24
.Lpair:
    /* The second insertion overwrites the first pair's oldest record.
     * Capture it before either write; WB_INPUT preserves r0:r1 and X. */
    ldd r0,Y+4
    ldd r1,Y+5
    ldd r26,Y+6
    ldd r27,Y+7
    WB_INPUT
    WB_INPUT
    .irp reg,4,5,6,7,8,9,10,11,12,13,14,15
    clr r\reg
    .endr
    movw r10,r0
    mov r21,r26
    mov r24,r27
    WB_MAC r7,r8,r9,-4
    mov r21,r10
    mov r24,r11
    clr r10
    clr r11
    WB_MAC r4,r5,r6,-10
    movw r26,r28
    adiw r26,32
    cp r28,r25
    brne .Lcursor
    sbiw r28,32
.Lcursor:
    /* Newest record belongs only to the second output pair. */
    WB_LOAD
    WB_MAC r13,r14,r15,-10
    WB_LOAD
    WB_MAC r10,r11,r12,-4
    /* Seven history records contribute to both output pairs. */
    WB_LOAD
    WB_MAC r7,r8,r9,-10
    WB_MAC r13,r14,r15,15
    WB_LOAD
    WB_MAC r4,r5,r6,-4
    WB_MAC r10,r11,r12,7
    WB_LOAD
    WB_MAC r7,r8,r9,15
    WB_MAC r13,r14,r15,-26
    WB_LOAD
    WB_MAC r4,r5,r6,7
    WB_MAC r10,r11,r12,-14
    WB_LOAD
    WB_MAC r7,r8,r9,-26
    WB_MAC r13,r14,r15,123
    WB_LOAD
    WB_MAC r4,r5,r6,-14
    WB_MAC r10,r11,r12,37
    WB_LOAD
    WB_MAC r7,r8,r9,123
    WB_MAC r13,r14,r15,37
    WB_LOAD
    WB_MAC r4,r5,r6,37
    WB_MAC r10,r11,r12,123
    WB_LOAD
    WB_MAC r7,r8,r9,37
    WB_MAC r13,r14,r15,-14
    WB_LOAD
    WB_MAC r4,r5,r6,123
    WB_MAC r10,r11,r12,-26
    WB_LOAD
    WB_MAC r7,r8,r9,-14
    WB_MAC r13,r14,r15,7
    WB_LOAD
    WB_MAC r4,r5,r6,-26
    WB_MAC r10,r11,r12,15
    WB_LOAD
    WB_MAC r7,r8,r9,7
    WB_MAC r13,r14,r15,-4
    WB_LOAD
    WB_MAC r4,r5,r6,15
    WB_MAC r10,r11,r12,-10
    movw r30,r22
    WB_FINISH r4,r5,r6
    WB_FINISH r7,r8,r9
    WB_FINISH r10,r11,r12
    WB_FINISH r13,r14,r15
    movw r22,r30
    dec r3
    breq .Ldone
    rjmp .Lpair
.Ldone:
    clr r1
    .irp reg,29,28,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2
    pop r\reg
    .endr
    ret
.size speex_wb_qmf40_avr,.-speex_wb_qmf40_avr
