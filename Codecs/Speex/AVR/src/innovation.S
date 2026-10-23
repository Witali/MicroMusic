/* Original ATmega328P NB3 vector kernel, 10 signed Flash shapes.
 * void speex_avr_innovation10(int16_t *out, const int32_t *pitch,
 *                            const int8_t *shape_flash, int32_t scale);
 * ABI: out r25:r24, pitch r23:r22, shape r21:r20, scale r19:r16.
 * NB3 scale is positive and <=121000000; shape*scale >>12 fits signed32.
 * floor(shape*scale/256) is formed with four signed 8x8 products, then
 * clearing its low nibble and shifting left 3 gives (shape*scale>>12)<<7.
 * This is exactly upstream MULT16_32_Q14(shape*4,scale)<<7 for this bound.
 * Pitch is already sanitized by upstream. Round >>14 and saturate +/-32767.
 * Callee-saved registers and r1 restored; interrupts remain enabled. */
.text
.global speex_avr_innovation10
.type speex_avr_innovation10, @function
speex_avr_innovation10:
    push r2
    push r3
    push r16
    push r17
    push r18
    push r19
    push r28
    push r29
    movw r28, r24
    movw r26, r22
    movw r30, r20
    clr r2
    ldi r20, 10
    mov r3, r20
.Linnovation_sample:
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
    ld r20, X+
    ld r21, X+
    ld r0, X+
    ld r1, X+
    lsl r20
    rol r21
    rol r0
    rol r1
    add r22, r20
    adc r23, r21
    adc r24, r0
    adc r25, r1
    ldi r20, 32
    add r23, r20
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
    sbc r25, r25
    tst r25
    brmi .Linnovation_negative
    or r24, r25
    brne .Linnovation_clip_positive
    sbrs r23, 7
    rjmp .Linnovation_store
.Linnovation_clip_positive:
    ldi r22, 255
    ldi r23, 127
    rjmp .Linnovation_store
.Linnovation_negative:
    cpi r25, 255
    brne .Linnovation_clip_negative
    cpi r24, 255
    brne .Linnovation_clip_negative
    sbrs r23, 7
    rjmp .Linnovation_clip_negative
    cpi r23, 128
    brne .Linnovation_store
    tst r22
    brne .Linnovation_store
.Linnovation_clip_negative:
    ldi r22, 1
    ldi r23, 128
.Linnovation_store:
    st Y+, r22
    st Y+, r23
    dec r3
    breq .Linnovation_done
    rjmp .Linnovation_sample
.Linnovation_done:
    clr r1
    pop r29
    pop r28
    pop r19
    pop r18
    pop r17
    pop r16
    pop r3
    pop r2
    ret
.size speex_avr_innovation10, .-speex_avr_innovation10
