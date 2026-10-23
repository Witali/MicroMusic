/* Exact Xiph product/MAC16_16 over a contiguous pitch-history segment.
 * First tap writes products; later taps accumulate into existing output.
 * A shared multiply loop avoids duplicating the two vector operations.
 * void speex_avr_pitch_add(int32_t *out, const int16_t *in, int16_t gain,
 *                          uint8_t count, uint8_t accumulate);
 * AVR ABI: out r25:r24, in r23:r22, gain r21:r20, count r18, accumulate r16 (copied to r19).
 * Preserve call-saved r2/r16/r17/Y; restore the C ABI zero register. */
.text
.global speex_avr_pitch_add
.type speex_avr_pitch_add, @function
speex_avr_pitch_add:
    tst r18
    brne .L_pitch_nonempty
    ret
.L_pitch_nonempty:
    mov r0, r20
    or r0, r21
    brne .L_pitch_nonzero
    /* Zero is an identity only for accumulation. A first/write pass must
     * initialize every output. r1 is zero on entry by the AVR-GCC ABI. */
    tst r16
    breq .L_pitch_clear
    ret
.L_pitch_clear:
    movw r26, r24
.L_pitch_clear_loop:
    st X+, r1
    st X+, r1
    st X+, r1
    st X+, r1
    dec r18
    brne .L_pitch_clear_loop
    ret
.L_pitch_nonzero:
    push r2
    push r16
    push r17
    push r28
    push r29
    mov r19, r16
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
    tst r19
    breq .L_pitch_store
    ldd r0, Y+0
    add r22, r0
    ldd r0, Y+1
    adc r23, r0
    ldd r0, Y+2
    adc r24, r0
    ldd r0, Y+3
    adc r25, r0
.L_pitch_store:
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
