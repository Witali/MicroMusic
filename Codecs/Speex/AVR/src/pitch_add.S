/* Exact Xiph MAC16_16 over a contiguous pitch-history segment.
 * void speex_avr_pitch_add(int32_t *out, const int16_t *in, int16_t gain,
 *                          uint8_t count);
 * AVR ABI: out r25:r24, in r23:r22, gain r21:r20, count r18.
 * Preserve call-saved r2/r16/r17/Y; restore the C ABI zero register. */
.text
.global speex_avr_pitch_add
.type speex_avr_pitch_add, @function
speex_avr_pitch_add:
    tst r18
    breq .L_pitch_return
    push r2
    push r16
    push r17
    push r28
    push r29
    movw r28, r24
    movw r26, r22
    clr r2
.L_pitch_loop:
    ld r16, X+
    ld r17, X+
    muls r17, r21
    movw r24, r0
    mul r16, r20
    movw r22, r0
    mulsu r17, r20
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    mulsu r21, r16
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    ldd r0, Y+0
    add r22, r0
    ldd r0, Y+1
    adc r23, r0
    ldd r0, Y+2
    adc r24, r0
    ldd r0, Y+3
    adc r25, r0
    st Y+, r22
    st Y+, r23
    st Y+, r24
    st Y+, r25
    dec r18
    brne .L_pitch_loop
    clr r1
    pop r29
    pop r28
    pop r17
    pop r16
    pop r2
.L_pitch_return:
    ret
.size speex_avr_pitch_add, .-speex_avr_pitch_add
