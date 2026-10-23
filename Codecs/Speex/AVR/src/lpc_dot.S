/* Original ATmega328P NB3 direct LPC synthesis, 40 samples/order 10.
 * void speex_avr_iir40(const int16_t *x, const int16_t *den,
 *                      int16_t *y, int32_t *state);
 * ABI arguments r25:r24, r23:r22, r21:r20, r19:r18; state is 60 zeroed bytes.
 * r6:x, r8:y, r10:den, r12:history base, r14:coef base; r16:history byte
 * cursor, r17:remaining samples. X/Z walk the dot product, Y writes state.
 * Arithmetic is modulo 2^32, then rounded >>13 and saturated to +/-32767.
 * All callee-saved registers and r1 restored; interrupts remain enabled. */
.text
.global speex_avr_iir40
.type speex_avr_iir40, @function
speex_avr_iir40:
    push r2
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
    movw r14, r18
    ldi r24, 40
    add r14, r24
    adc r15, r1
    clr r2
    clr r16
    ldi r17, 40
.Lsample:
    movw r26, r14
    movw r30, r12
    add r30, r16
    adc r31, r2
    adiw r30, 20
    clr r22
    clr r23
    clr r24
    clr r25
    .rept 10
    ld r18, X+
    ld r19, X+
    ld r21, -Z
    ld r20, -Z
    muls r19, r21
    add r24, r0
    adc r25, r1
    mul r18, r20
    add r22, r0
    adc r23, r1
    adc r24, r2
    adc r25, r2
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
    .endr
    /* PSHR32(sum,13), preserving wrap when adding the rounding bias. */
    ldi r18, 16
    add r23, r18
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
    sbc r25, r25
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
    adc r25, r20
    tst r25
    brmi .Lnegative
    or r24, r25
    brne .Lclip_positive
    sbrs r23, 7
    rjmp .Lstore
.Lclip_positive:
    ldi r22, 255
    ldi r23, 127
    rjmp .Lstore
.Lnegative:
    cpi r25, 255
    brne .Lclip_negative
    cpi r24, 255
    brne .Lclip_negative
    sbrs r23, 7
    rjmp .Lclip_negative
    cpi r23, 128
    brne .Lstore
    tst r22
    brne .Lstore
.Lclip_negative:
    ldi r22, 1
    ldi r23, 128
.Lstore:
    movw r30, r8
    st Z+, r22
    st Z+, r23
    movw r8, r30
    com r22
    com r23
    subi r22, 255
    sbci r23, 255
    movw r28, r12
    add r28, r16
    adc r29, r2
    std Y+0, r22
    std Y+1, r23
    std Y+20, r22
    std Y+21, r23
    /* Sample 0 uses all previous coefficients; sample 1 uses new den[0],
     * etc. The transposed recurrence ages coefficients in exactly this way. */
    cpi r17, 31
    brlo .Lcoeff_done
    movw r26, r10
    ld r18, X+
    ld r19, X+
    movw r10, r26
    std Y+40, r18
    std Y+41, r19
.Lcoeff_done:
    subi r16, -2
    cpi r16, 20
    brlo .Lcursor_done
    clr r16
.Lcursor_done:
    dec r17
    breq .Ldone
    rjmp .Lsample
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
    pop r2
    ret
.size speex_avr_iir40, .-speex_avr_iir40
