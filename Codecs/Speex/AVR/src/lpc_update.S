/* Speex NB8: hand-written ATmega328P transposed LPC state update.
 * void speex_nb8_lpc_update_asm(int32_t *mem, const int16_t *coef, int16_t neg_y);
 * ABI: mem r25:r24, coef r23:r22, neg_y r21:r20.
 * Computes mem[j] = (mem[j+1] + coef[j]*neg_y) mod 2^32 for j=0..8,
 * mem[9] = coef[9]*neg_y, matching the C reference.
 * Clobbers only call-clobbered registers plus r2/Y, which are saved.
 * r1 is restored to zero; no reliance on external SRAM or tables.
 */
.text
.global speex_nb8_lpc_update_asm
.type speex_nb8_lpc_update_asm, @function
speex_nb8_lpc_update_asm:
    push r2
    push r28
    push r29
    movw r28, r24        /* Y = mem */
    movw r26, r22        /* X = coef */
    clr r2               /* carry addend = 0 */
    .rept 9
    ld r18, X+           /* coef low */
    ld r19, X+           /* coef high */
    muls r19, r21        /* sign-hi * sign-hi */
    movw r24, r0
    mul r18, r20         /* unsigned low * low */
    movw r22, r0
    mulsu r19, r20       /* sign-hi coef * low neg */
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    mulsu r21, r18       /* sign-hi neg * low coef */
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    /* mem[j] = product + mem[j+1], modulo 2^32 */
    ldd r18, Y+4
    add r22, r18
    ldd r18, Y+5
    adc r23, r18
    ldd r18, Y+6
    adc r24, r18
    ldd r18, Y+7
    adc r25, r18
    std Y+0, r22
    std Y+1, r23
    std Y+2, r24
    std Y+3, r25
    adiw r28, 4
    .endr
    /* Final coefficient, no mem[j+1] */
    ld r18, X+
    ld r19, X+
    muls r19, r21
    movw r24, r0
    mul r18, r20
    movw r22, r0
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
    std Y+0, r22
    std Y+1, r23
    std Y+2, r24
    std Y+3, r25
    clr r1
    pop r29
    pop r28
    pop r2
    ret
.size speex_nb8_lpc_update_asm, .-speex_nb8_lpc_update_asm
