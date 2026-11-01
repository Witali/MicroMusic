/* Original project exact mean transform, classic AVR5 / GNU ABI.
 * old r24:25, value r22:23 -> signed16 result r24:25.
 * 26214+6554=32768, so old+round(6554*(value-old)/32768).
 * Wrapped signed16 delta needs +/-2*6554 when subtraction overflows.
 * Four MUL instructions replace two general signed16 products (eight MUL).
 * Only call-clobbered registers/flags change; r1 cleared, no local stack,
 * memory accesses or interrupt masking. Explicit C fallback in .h. */
.text
.global speex_low_mean_avr
.type speex_low_mean_avr,@function
speex_low_mean_avr:
    movw r26,r24
    sub r22,r24
    sbc r23,r25
    ldi r24,0
    ldi r25,0
    brvc .Lmean_base
    ldi r24,lo8(13108)
    ldi r25,hi8(13108)
    sbrc r23,7
    rjmp .Lmean_base
    ldi r24,lo8(-13108)
    ldi r25,hi8(-13108)
.Lmean_base:
    add r24,r26
    adc r25,r27
    ldi r18,154
    ldi r19,25
    muls r23,r19
    movw r26,r0
    mul r22,r18
    movw r20,r0
    mulsu r23,r18
    clr r18
    sbc r27,r18
    add r21,r0
    adc r26,r1
    adc r27,r18
    mul r22,r19
    add r21,r0
    adc r26,r1
    adc r27,r18
    clr r1
    ldi r19,64
    add r21,r19
    adc r26,r1
    adc r27,r1
    lsl r21
    rol r26
    rol r27
    add r24,r26
    adc r25,r27
    ret
.size speex_low_mean_avr,.-speex_low_mean_avr
