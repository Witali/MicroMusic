/* Exact Xiph product/MAC16_16 into packed signed24 over a contiguous pitch-history segment.
 * NB3 gains are signed8 values (-50..97 from the codebook+32) with their common *128 deferred to innovation.
 * First tap writes products; later taps accumulate into existing output.
 * A shared multiply loop avoids duplicating the two vector operations.
 * void speex_avr_pitch_add24(uint8_t *out, const int16_t *in, int8_t gain,
 *                          uint8_t count, uint8_t accumulate);
 * AVR ABI: out r25:r24, in r23:r22, gain r20, count r18, accumulate r16.
 * Keep invariant write/add mode in SREG.T (GCC ISRs save/restore SREG).
 * Preserve call-saved r17/Y; restore the C ABI zero register. */
.text
.global speex_avr_pitch_add24
.type speex_avr_pitch_add24, @function
speex_avr_pitch_add24:
    tst r18
    brne .L_pitch_nonempty
    ret
.L_pitch_nonempty:
    tst r20
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
    dec r18
    brne .L_pitch_clear_loop
    ret
.L_pitch_nonzero:
    push r17
    push r28
    push r29
    /* Any nonzero accumulate value sets T; r1 is still the entry ABI zero.
     * These three cycles replace a test at every sample and free r19. */
    clt
    cpse r16, r1
    set
    mov r17, r18
    movw r28, r24
    movw r26, r22
    clr r21             /* zero for signed-product correction */
.L_pitch_loop:
    ld r18, X+
    ld r19, X+
    muls r19, r20
    movw r24, r0
    /* Exact signed8 gain * signed16 input in r25:r23. */
    mulsu r20, r18
    mov r23, r0
    sbc r25, r21
    add r24, r1
    adc r25, r21
    brtc .L_pitch_store
    ldd r0, Y+0
    add r23, r0
    ldd r0, Y+1
    adc r24, r0
    ldd r0, Y+2
    adc r25, r0
.L_pitch_store:
    st Y+, r23
    st Y+, r24
    st Y+, r25
    dec r17
    brne .L_pitch_loop
    clr r1
    pop r29
    pop r28
    pop r17
.L_pitch_return:
    ret
.size speex_avr_pitch_add24, .-speex_avr_pitch_add24
