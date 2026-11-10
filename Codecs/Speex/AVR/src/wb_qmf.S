/* Normalized 16-tap Q7 QMF, two input pairs per iteration.
 * Same exact signed24 arithmetic as wb_qmf.c: 236*32768+32 < 2^23.
 * Shared history loads feed four accumulators; no additional state.
 * ABI: low r24, high r22, out r20, 64-byte state r18; fixed 40 pairs.
 * Split Llo,Lhi,Hlo,Hhi groups: E0 r4..7, O0 r8..11,
 * E1 r12..15, O1 r16..19. Low/high pointers r16..19 spill four bytes
 * across the MAC section; out r22:23, zero r2, count r3, cursor end r25.
 * Loading both input pairs before four output stores preserves high=out+40.
 * All callee-saved registers and r1 restored; interrupts remain enabled. */
.text

/* The loaded signed16 value r24:r21 is reused for adjacent output pairs. */
.macro WB_LOAD
    ld r24,-X
    ld r21,-X
.endm
/* Split exact accumulation: L is biased unsigned16, H is signed16-54.
 * Llo,Lhi,Hlo,Hhi use four registers. r30 holds54 during first products. */
.macro WB_MAC a,b,c,d,coefficient,first=0
    ldi r20,lo8(\coefficient)
    muls r20,r24
    .if \first
    movw \c,r0
    sub \c,r30
    sbc \d,r2
    .else
    add \c,r0
    adc \d,r1
    .endif
    mulsu r20,r21
    .if \first
    movw \a,r0
    add \b,r30
    .else
    add \a,r0
    adc \b,r1
    .endif
.endm
.macro WB_PAIR_7_MINUS14 a,b,c,d,e,f,g,h
    ldi r20,7
    muls r20,r24
    add \c,r0
    adc \d,r1
    lsl r0
    rol r1
    sub \g,r0
    sbc \h,r1
    mulsu r20,r21
    add \a,r0
    adc \b,r1
    lsl r0
    rol r1
    sub \e,r0
    sbc \f,r1
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
    rcall qmf_input_private
    rcall qmf_input_private
    push r16
    push r17
    push r18
    push r19
    ldi r30,54
    /* Consume the saved oldest difference before MUL clobbers r0:r1,
     * then its sum. Each split accumulator starts with H bias -54
     * and L bias +13824, using the shared r30 constant. */
    mov r21,r0
    mov r24,r1
    WB_MAC r4,r5,r6,r7,-10,1
    mov r21,r26
    mov r24,r27
    WB_MAC r8,r9,r10,r11,-4,2
    movw r26,r28
    adiw r26,32
    cp r28,r25
    brne .Lcursor
    sbiw r28,32
.Lcursor:
    /* Newest record belongs only to the second output pair. */
    WB_LOAD
    WB_MAC r16,r17,r18,r19,-10,2
    WB_LOAD
    WB_MAC r12,r13,r14,r15,-4,1
    /* Seven history records contribute to both output pairs. */
    WB_LOAD
    WB_MAC r8,r9,r10,r11,-10
    WB_MAC r16,r17,r18,r19,15
    WB_LOAD
    WB_MAC r4,r5,r6,r7,-4
    WB_MAC r12,r13,r14,r15,7
    WB_LOAD
    WB_MAC r8,r9,r10,r11,15
    WB_MAC r16,r17,r18,r19,-26
    WB_LOAD
    WB_PAIR_7_MINUS14 r4,r5,r6,r7,r12,r13,r14,r15
    WB_LOAD
    WB_MAC r8,r9,r10,r11,-26
    WB_MAC r16,r17,r18,r19,123
    WB_LOAD
    WB_MAC r4,r5,r6,r7,-14
    WB_MAC r12,r13,r14,r15,37
    WB_LOAD
    WB_MAC r8,r9,r10,r11,123
    WB_MAC r16,r17,r18,r19,37
    WB_LOAD
    WB_MAC r4,r5,r6,r7,37
    WB_MAC r12,r13,r14,r15,123
    WB_LOAD
    WB_MAC r8,r9,r10,r11,37
    WB_MAC r16,r17,r18,r19,-14
    WB_LOAD
    WB_MAC r4,r5,r6,r7,123
    WB_MAC r12,r13,r14,r15,-26
    WB_LOAD
    WB_PAIR_7_MINUS14 r16,r17,r18,r19,r8,r9,r10,r11
    WB_LOAD
    WB_MAC r4,r5,r6,r7,-26
    WB_MAC r12,r13,r14,r15,15
    WB_LOAD
    WB_MAC r8,r9,r10,r11,7
    WB_MAC r16,r17,r18,r19,-4
    WB_LOAD
    WB_MAC r12,r13,r14,r15,-10
    WB_MAC r4,r5,r6,r7,15
    movw r30,r22
    mov r0,r25
    add r6,r5
    adc r7,r2
    mov r20,r4
    movw r24,r6
    rcall qmf_finish_private
    add r10,r9
    adc r11,r2
    mov r20,r8
    movw r24,r10
    rcall qmf_finish_private
    add r14,r13
    adc r15,r2
    mov r20,r12
    movw r24,r14
    rcall qmf_finish_private
    add r18,r17
    adc r19,r2
    mov r20,r16
    movw r24,r18
    rcall qmf_finish_private
    mov r25,r0
    movw r22,r30
    pop r19
    pop r18
    pop r17
    pop r16
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

/* Private fixed-register helper: preserves r0:r1 and X, may keep dirty r1. */
.type qmf_input_private,@function
qmf_input_private:
    WB_INPUT
    ret
.size qmf_input_private,.-qmf_input_private

/* Private: signed24 input r20,r24,r25; scratch r21; output via Z.
 * r0 retains the main loop's cursor limit across all four calls. */
.type qmf_finish_private,@function
qmf_finish_private:
    ldi r21,32
    add r20,r21
    adc r24,r2
    adc r25,r2
    mov r21,r25
    andi r21,224
    breq .LFconvert
    cpi r21,224
    breq .LFconvert
    sbrc r25,7
    rjmp .LFclipneg
    ldi r20,255
    ldi r24,127
    rjmp .LFstore
.LFconvert:
    .rept 2
    lsl r20
    rol r24
    rol r25
    .endr
    mov r20,r24
    mov r24,r25
    cpi r24,128
    brne .LFstore
    tst r20
    brne .LFstore
.LFclipneg:
    ldi r20,1
    ldi r24,128
.LFstore:
    st Z+,r20
    st Z+,r24
    ret
.size qmf_finish_private,.-qmf_finish_private
