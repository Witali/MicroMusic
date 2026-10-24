/* Original exact NB3 excitation instruction schedules for classic AVR MUL.
 * GNU AVR ABI: r2=0, r8=32; dot uses history a=r5:r4, b=r7:r6,
 * X=next word, gains r10/r11/r12; emits signed24 adaptive in r15:r13.
 * Transform consumes that sum, scale r19:r16, Z=Flash shape, Y=PCM output;
 * preserves X, r3..r12, r16..r19 and SREG.T. r0/r1/r20..r25 are scratch.
 * r1 must be cleared by the enclosing ABI entry before returning to C.
 * GAS macros share source arithmetic; the rolling and dedicated forty-sample
 * loops expand to separate machine bodies to avoid inner-loop mode dispatch.
 * Bounds: nonnegative scale<=121000000; signed8 gains with L1<=147;
 * signed16 history; original pitch/output clamps, Q14 floors and rounding. */
    .macro long_product lo, hi, gain
    mov r20, \gain
    mov r21, \hi
    muls r21, r20
    movw r24, r0
    mov r21, \lo
    mulsu r20, r21
    mov r23, r0
    sbc r25, r2
    add r24, r1
    adc r25, r2
    .endm

    .macro speex_nb3_long_dot
    long_product r4,r5,r10
    movw r14, r24
    mov r13, r23
    long_product r6,r7,r11
    add r13, r23
    adc r14, r24
    adc r15, r25
    /* a is dead after its product; b is dead after the second product.
     * Advance the window before the final MAC and load c directly into b. */
    movw r4, r6
    ld r6, X+
    ld r7, X+
    long_product r6,r7,r12
    add r13, r23
    adc r14, r24
    adc r15, r25
    .endm

    .macro speex_nb3_innovation_transform
    lpm r20, Z+
    mulsu r20, r16
    mov r22, r1
    sbc r23, r23
    mov r24, r23
    mov r25, r23
    mulsu r20, r17
    sbc r24, r2
    sbc r25, r2
    add r22, r0
    adc r23, r1
    adc r24, r2
    adc r25, r2
    mulsu r20, r18
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    mulsu r20, r19
    add r24, r0
    adc r25, r1
    andi r22, 240
    .rept 3
    lsl r22
    rol r23
    rol r24
    rol r25
    .endr
    /* Clamp signed24 to +/-2048000 (0x1f4000 / 0xe0c000).
     * Compare signed high bytes first; only boundary bytes need lower tests. */
    ldi r20, 31
    cp r20, r15
    brlt .Lpitch_clip_positive\@
    brne .Lpitch_check_lower\@
    ldi r20, 64
    cp r20, r14
    brlo .Lpitch_clip_positive\@
    brne .Lpitch_ready\@
    tst r13
    brne .Lpitch_clip_positive\@
    rjmp .Lpitch_ready\@
.Lpitch_check_lower\@:
    ldi r20, 224
    cp r15, r20
    brlt .Lpitch_clip_negative\@
    brne .Lpitch_ready\@
    ldi r20, 192
    cp r14, r20
    brlo .Lpitch_clip_negative\@
    rjmp .Lpitch_ready\@
.Lpitch_clip_positive\@:
    mov r13, r2
    ldi r20, 64
    mov r14, r20
    ldi r20, 31
    mov r15, r20
    rjmp .Lpitch_ready\@
.Lpitch_clip_negative\@:
    mov r13, r2
    ldi r20, 192
    mov r14, r20
    ldi r20, 224
    mov r15, r20
.Lpitch_ready\@:
    /* pitch*2*128 has a zero low byte. The lower innovation byte stays
     * unchanged, and ADD (not ADC) starts the upper-byte carry chain. */
    add r23, r13
    adc r24, r14
    adc r25, r15
    add r23, r8
    adc r24, r2
    adc r25, r2
    /* Arithmetic >>14 through left alignment and carry. */
    lsl r23
    rol r24
    rol r25
    sbc r22, r22
    lsl r23
    rol r24
    rol r25
    rol r22
    mov r0, r22
    mov r22, r24
    mov r23, r25
    mov r24, r0
    /* Rounded wrapped signed32 >>14 fits signed18; do not materialize
     * a fourth sign-extension byte merely to saturate the result to s16. */
    tst r24
    brmi .Linnovation_negative\@
    brne .Linnovation_clip_positive\@
    sbrs r23, 7
    rjmp .Linnovation_store\@
.Linnovation_clip_positive\@:
    ldi r22, 255
    ldi r23, 127
    rjmp .Linnovation_store\@
.Linnovation_negative\@:
    cpi r24, 255
    brne .Linnovation_clip_negative\@
    sbrs r23, 7
    rjmp .Linnovation_clip_negative\@
    cpi r23, 128
    brne .Linnovation_store\@
    tst r22
    brne .Linnovation_store\@
.Linnovation_clip_negative\@:
    ldi r22, 1
    ldi r23, 128
.Linnovation_store\@:
    st Y+, r22
    st Y+, r23
    .endm
