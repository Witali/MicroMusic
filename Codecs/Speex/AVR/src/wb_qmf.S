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
/* first=1 initializes with separate moves; first=2 uses an aligned MOVW.
 * Initialization must ADD the middle byte: MOV of the low byte does not
 * clear the carry left by the sign correction. Later taps propagate ADC. */
.macro WB_MAC a,b,c,coefficient,first=0
    ldi r20,lo8(\coefficient)
    muls r20,r24
    .if \first
    .if \first == 2
    movw \b,r0
    .else
    mov \b,r0
    mov \c,r1
    .endif
    .else
    add \b,r0
    adc \c,r1
    .endif
    mulsu r20,r21
    sbc \c,r2
    .if \first
    mov \a,r0
    add \b,r1
    .else
    add \a,r0
    adc \b,r1
    .endif
    adc \c,r2
.endm
/* P=7*x fits signed24. Z and r20 are dead scratch until WB_FINISH. */
.macro WB_PAIR_7_MINUS14 a,b,c,d,e,f
    ldi r20,7
    muls r20,r24
    movw r30,r0
    mulsu r20,r21
    mov r20,r0
    add r30,r1
    adc r31,r2
    add \a,r20
    adc \b,r30
    adc \c,r31
    lsl r20
    rol r30
    rol r31
    sub \d,r20
    sbc \e,r30
    sbc \f,r31
.endm
/* P=10*x is even: P+(P>>1) is exactly 15*x for both signs. */
.macro WB_PAIR_MINUS10_15 a,b,c,d,e,f
    ldi r20,10
    muls r20,r24
    movw r30,r0
    mulsu r20,r21
    mov r20,r0
    add r30,r1
    adc r31,r2
    sub \a,r20
    sbc \b,r30
    sbc \c,r31
    add \d,r20
    adc \e,r30
    adc \f,r31
    asr r31
    ror r30
    ror r20
    add \d,r20
    adc \e,r30
    adc \f,r31
.endm
/* r20=128 on entry and exit, so adjacent inputs share the bias constant. */
.macro WB_INPUT
    movw r30,r16
    ld r4,Z+
    ld r5,Z+
    movw r16,r30
    movw r30,r18
    ld r7,Z+
    ld r8,Z+
    movw r18,r30
    /* Bias signed16 into unsigned16. The SUB borrow is the sign bit of
     * the exact signed17 difference; the ADD carry is bit16 of the sum.
     * ROR consumes that bit, retaining floor rounding for negative odds.
     * Re-bias only the half-sum; the difference cancels both biases. */
    eor r5,r20
    eor r8,r20
    movw r10,r4
    sub r10,r7
    sbc r11,r8
    ror r11
    ror r10
    add r4,r7
    adc r5,r8
    ror r5
    ror r4
    eor r5,r20
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
    /* A rounded signed24 value fits the signed16 Q6 output when its
     * top three bits are all zero or all one. Check before left alignment. */
    mov r20,\c
    andi r20,224
    breq .Lconvert\@
    cpi r20,224
    breq .Lconvert\@
    sbrc \c,7
    rjmp .Lclipneg\@
    ldi r21,255
    ldi r24,127
    rjmp .Lstore\@
.Lconvert\@:
    .rept 2
    lsl \a
    rol \b
    rol \c
    .endr
    mov r21,\b
    mov r24,\c
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
    ldi r20,128
    WB_INPUT
    WB_INPUT
    /* The first tap initializes each signed24 accumulator. Consume the
     * saved oldest difference before MUL clobbers r0:r1, then its sum.
     * This also avoids an intermediate copy through r10:r11. */
    mov r21,r0
    mov r24,r1
    WB_MAC r4,r5,r6,-10,1
    mov r21,r26
    mov r24,r27
    WB_MAC r7,r8,r9,-4,2
    movw r26,r28
    adiw r26,32
    cp r28,r25
    brne .Lcursor
    sbiw r28,32
.Lcursor:
    /* Newest record belongs only to the second output pair. */
    WB_LOAD
    WB_MAC r13,r14,r15,-10,2
    WB_LOAD
    WB_MAC r10,r11,r12,-4,1
    /* Seven history records contribute to both output pairs. */
    WB_LOAD
    WB_PAIR_MINUS10_15 r7,r8,r9,r13,r14,r15
    WB_LOAD
    WB_MAC r4,r5,r6,-4
    WB_MAC r10,r11,r12,7
    WB_LOAD
    WB_MAC r7,r8,r9,15
    WB_MAC r13,r14,r15,-26
    WB_LOAD
    WB_PAIR_7_MINUS14 r4,r5,r6,r10,r11,r12
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
    WB_PAIR_7_MINUS14 r13,r14,r15,r7,r8,r9
    WB_LOAD
    WB_MAC r4,r5,r6,-26
    WB_MAC r10,r11,r12,15
    WB_LOAD
    WB_MAC r7,r8,r9,7
    WB_MAC r13,r14,r15,-4
    WB_LOAD
    WB_PAIR_MINUS10_15 r10,r11,r12,r4,r5,r6
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
