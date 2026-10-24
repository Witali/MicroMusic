/* Original ATmega328P NB3 direct LPC synthesis, 40 samples/order 10.
 * void speex_avr_iir40(const int16_t *x, const int16_t *den,
 *                      int16_t *y, int32_t *state);
 * ABI arguments r25:r24, r23:r22, r21:r20, r19:r18; state is 60 zeroed bytes.
 * r6:x, r8:y, r10:den, r12:history base, r14:coef base; r16:history end
 * low byte, r17:remaining phase samples. After ten samples r10/r14 cache
 * coefficient words 0/1; all ten coefficient ages then equal the new den.
 * X/Z walk the dot product; Y retains the
 * history write cursor, advanced by the two stores and reset each ten samples.
 * Arithmetic is modulo 2^32, then rounded >>13 and saturated to +/-32767.
 * All callee-saved registers and r1 restored; interrupts remain enabled. */
.text
/* Source macros share the exact arithmetic without per-tap CALL overhead. */
.macro IIR_MAC coefficient
    .ifc \coefficient,memory
    ld r18, X+
    ld r19, X+
    .else
    movw r18, \coefficient
    .endif
    ld r21, -Z
    ld r20, -Z
    /* AVR201 method B: signed 16x16 plus accumulator modulo 2^32. */
    muls r19, r21
    movw r4, r0
    mul r18, r20
    add r22, r0
    adc r23, r1
    adc r24, r4
    adc r25, r5
    mulsu r19, r20
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    mulsu r21, r18
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
.endm
.macro IIR_FINISH age
    /* PSHR32(sum,13), preserving wrap when adding the rounding bias. */
    add r23,r3
    adc r24, r2
    adc r25, r2
    lsl r23
    rol r24
    rol r25
    sbc r22, r22
    .rept 2
    lsl r23
    rol r24
    rol r25
    rol r22
    .endr
    mov r0, r22
    mov r22, r24
    mov r23, r25
    mov r24, r0
    /* Rounded signed32 >>13 lies in [-262144,262143]. Adding signed16
     * input lies in [-294912,294910], so signed24 is sufficient. */
    /* Add sign-extended input before saturation. Read before writing y so
     * the upstream in-place x==y case is supported. */
    movw r30, r6
    ld r18, Z+
    ld r19, Z+
    movw r6, r30
    mov r20, r19
    lsl r20
    sbc r20, r20
    add r22, r18
    adc r23, r19
    adc r24, r20
    tst r24
    brmi .Lnegative\@
    brne .Lclip_positive\@
    sbrs r23, 7
    rjmp .Lstore\@
.Lclip_positive\@:
    ldi r22, 255
    ldi r23, 127
    rjmp .Lstore\@
.Lnegative\@:
    cpi r24, 255
    brne .Lclip_negative\@
    sbrs r23, 7
    rjmp .Lclip_negative\@
    cpi r23, 128
    brne .Lstore\@
    tst r22
    brne .Lstore\@
.Lclip_negative\@:
    ldi r22, 1
    ldi r23, 128
.Lstore\@:
    movw r30, r8
    st Z+, r22
    st Z+, r23
    movw r8, r30
    com r22
    com r23
    subi r22, 255
    sbci r23, 255
    /* Y advances to the next sample without a separate address calculation.
     * Mirror/age offsets compensate for the two postincrements. */
    st Y+,r22
    st Y+,r23
    std Y+18,r22
    std Y+19,r23
    /* Sample 0 uses all previous coefficients; sample 1 uses new den[0],
     * etc. The transposed recurrence ages coefficients in exactly this way. */
    .if \age
    movw r26, r10
    ld r18, X+
    ld r19, X+
    movw r10, r26
    std Y+38,r18
    std Y+39,r19
    .endif
    cp r28,r16
    brne .Lcursor_done\@
    movw r28,r12
.Lcursor_done\@:
.endm
.global speex_avr_iir40
.type speex_avr_iir40, @function
speex_avr_iir40:
    push r2
    push r3
    push r4
    push r5
    push r6
    push r7
    push r8
    push r9
    push r10
    push r11
    push r12
    push r13
    push r14
    push r15
    push r16
    push r17
    push r28
    push r29
    movw r6, r24
    movw r10, r22
    movw r8, r20
    movw r12, r18
    movw r28,r18
    movw r14, r18
    ldi r24, 40
    add r14, r24
    adc r15, r1
    clr r2
    /* One rounding constant for the whole block; r3 survives every MAC. */
    ldi r18,16
    mov r3,r18
    /* Y traverses exactly twenty bytes, so its low byte reaches the low
     * end byte only after ten words, including across a 256-byte page. */
    mov r16,r12
    subi r16,-20
    ldi r17, 10
.Lwarm_sample:
    movw r26, r14
    movw r30, r28
    adiw r30, 20
    clr r22
    clr r23
    clr r24
    clr r25
    .rept 10
    IIR_MAC memory
    .endr
    IIR_FINISH 1
    dec r17
    breq .Lsteady_setup
    rjmp .Lwarm_sample
.Lsteady_setup:
    /* Age updates are complete. Reuse dead den/base registers for two LPC
     * words; history writes are confined to state[0..39]. No extra SRAM. */
    movw r26, r14
    ld r10, X+
    ld r11, X+
    ld r14, X+
    ld r15, X+
    ldi r17, 30
.Lsteady_sample:
    movw r26, r12
    adiw r26, 44
    movw r30, r28
    adiw r30, 20
    clr r22
    clr r23
    clr r24
    clr r25
    IIR_MAC r10
    IIR_MAC r14
    .rept 8
    IIR_MAC memory
    .endr
    IIR_FINISH 0
    dec r17
    breq .Ldone
    rjmp .Lsteady_sample
.Ldone:
    clr r1
    pop r29
    pop r28
    pop r17
    pop r16
    pop r15
    pop r14
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop r7
    pop r6
    pop r5
    pop r4
    pop r3
    pop r2
    ret
.size speex_avr_iir40, .-speex_avr_iir40
