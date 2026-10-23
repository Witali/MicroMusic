/* Exact Xiph product/MAC16_16 over a contiguous pitch-history segment.
 * NB3 gains are signed8 values (-50..97 from the codebook+32) scaled by 128.
 * First tap writes products; later taps accumulate into existing output.
 * A shared multiply loop avoids duplicating the two vector operations.
 * void speex_avr_pitch_add(int32_t *out, const int16_t *in, int16_t gain,
 *                          uint8_t count, uint8_t accumulate);
 * AVR ABI: out r25:r24, in r23:r22, gain r21:r20, count r18, accumulate r16 (copied to r19).
 * Preserve call-saved r16/r17/Y; restore the C ABI zero register. */
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
    push r16
    push r17
    push r28
    push r29
    mov r19, r16
    movw r28, r24
    movw r26, r22
    /* Extract signed8 gain from its <<7 representation. r20 becomes zero
     * and serves as the multiply carry/sign-correction zero throughout. */
    lsl r20
    rol r21
.L_pitch_loop:
    ld r16, X+
    ld r17, X+
    muls r17, r21
    movw r24, r0
    /* signed8 gain * signed16 input in r25:r23, shifted left by one byte.
     * Then arithmetic >>1 produces the exact original gain*input*128. */
    mulsu r21, r16
    mov r23, r0
    sbc r25, r20
    add r24, r1
    adc r25, r20
    clr r22
    asr r25
    ror r24
    ror r23
    ror r22
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
.L_pitch_return:
    ret
.size speex_avr_pitch_add, .-speex_avr_pitch_add
