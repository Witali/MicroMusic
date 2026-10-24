/* NB3 zero-adaptive quantization: shape in Flash through Z, positive
 * scale r19:r16 <=121000000, zero r2; output signed16 r24:r23.
 * Same byte arithmetic as nb3_c_math.h. Clobbers r0:r1,r20,r22..r25.
 * Shared by NB and fused WB without per-sample subroutine overhead. */
.macro SPEEX_ZERO_SHAPE bias
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
    add r23, \bias
    adc r24, r2
    adc r25, r2
    .rept 3
    asr r25
    ror r24
    ror r23
    .endr
.endm
