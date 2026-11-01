/* Exact rounded HB1 gain divide for classic AVR / GNU ABI.
 * Input energy r22..25 in 0..904448, ratio r20:21 in 1..32767.
 * Rounded numerator <=920831 <2^20. Divide its high nibble first, then
 * process sixteen low bits with a uint16 remainder. Before each shift
 * remainder < ratio <=32767, so 2*remainder+bit <=65533 fits 16 bits.
 * Result r22..25 is nonnegative signed32. Only call-clobbered registers
 * r18..26 and flags change; r1 and all callee-saved registers are untouched.
 * No stack, hardware memory access or interrupt masking. C fallback in .h. */
.text
.global speex_wb_gain_div_avr
.type speex_wb_gain_div_avr,@function
speex_wb_gain_div_avr:
    movw r18,r20
    lsr r19
    ror r18
    add r22,r18
    adc r23,r19
    adc r24,r1
    mov r18,r24
    clr r19
    clr r24
    clr r25
.Lhigh:
    cp r18,r20
    cpc r19,r21
    brcs .Llow
    sub r18,r20
    sbc r19,r21
    inc r24
    rjmp .Lhigh
.Llow:
    ldi r26,16
.Lbit:
    lsl r22
    rol r23
    rol r18
    rol r19
    cp r18,r20
    cpc r19,r21
    brcs .Lnext
    sub r18,r20
    sbc r19,r21
    ori r22,1
.Lnext:
    dec r26
    brne .Lbit
    ret
.size speex_wb_gain_div_avr,.-speex_wb_gain_div_avr
