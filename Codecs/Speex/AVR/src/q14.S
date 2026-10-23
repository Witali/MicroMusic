/* Exact generic Xiph MULT16_32_Q14 in one AVR-GCC ABI subroutine.
 * int32_t speex_avr_mul16_32_q14(int16_t a, int32_t b);
 * a r25:r24, b r23:r20, result r25:r22. No callee-saved registers, restore r1.
 * Upstream casts b>>14 to signed16: its effective operand is signed30(b).
 * Form the signed 48-bit product in r27:r22, align left by 2 and discard
 * 16 low bits. This retains upstream's floor, including negative operands
 * and all four possible values of the ignored top two input bits.
 * Original register/carry schedule; no interrupt masking or RAM scratch. */
.section .text.speex_avr_mul16_32_q14,"ax",@progbits
.global speex_avr_mul16_32_q14
.type speex_avr_mul16_32_q14, @function
speex_avr_mul16_32_q14:
    /* Generic entry normalizes signed30 before tail-calling the same core. */
    lsl r23
    lsl r23
    asr r23
    asr r23
    rjmp speex_avr_lsp_mul_q14
.size speex_avr_mul16_32_q14, .-speex_avr_mul16_32_q14

/* Fast entry requires -2^29 <= b < 2^29. Order-10 polynomial inputs have
 * |b| <= 73400331 by the absolute-value recurrence bound in compact_lsp. */
.section .text.speex_avr_lsp_mul_q14,"ax",@progbits
.global speex_avr_lsp_mul_q14
.type speex_avr_lsp_mul_q14, @function
speex_avr_lsp_mul_q14:
    movw r18, r24       /* a */
    movw r30, r22       /* original high word of b */
    clr r26             /* low product's temporary zero */
    /* Signed16 a times unsigned16 low b, exact signed32 result. */
    mulsu r19, r21
    movw r24, r0
    mul r18, r20
    movw r22, r0
    mulsu r19, r20
    sbc r25, r26
    add r23, r0
    adc r24, r1
    adc r25, r26
    mul r18, r21
    add r23, r0
    adc r24, r1
    adc r25, r26
    mov r26, r25
    lsl r26
    sbc r26, r26
    mov r27, r26
    movw r20, r30
    clr r30             /* high word moved; Z low is now a free zero */
    /* Add signed16 a * signed16 high b at product bit 16. */
    muls r19, r21
    add r26, r0
    adc r27, r1
    mul r18, r20
    add r24, r0
    adc r25, r1
    adc r26, r30
    adc r27, r30
    mulsu r19, r20
    sbc r27, r30
    add r25, r0
    adc r26, r1
    adc r27, r30
    mulsu r21, r18
    sbc r27, r30
    add r25, r0
    adc r26, r1
    adc r27, r30
    .rept 2
    lsl r23
    rol r24
    rol r25
    rol r26
    rol r27
    .endr
    movw r22, r24
    movw r24, r26
    clr r1
    ret
.size speex_avr_lsp_mul_q14, .-speex_avr_lsp_mul_q14
