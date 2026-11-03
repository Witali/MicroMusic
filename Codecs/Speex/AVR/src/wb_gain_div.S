/* Exact rounded HB1 gain divide for classic AVR / GNU ABI.
 * Input energy r22..25 in 0..904448, ratio r20:21 in 1..32767.
 * Rounded numerator <=920831 <2^20. Divide its high nibble first, then
 * process sixteen low bits with a uint16 remainder. Before each shift
 * remainder < ratio <=32767, so 2*remainder+bit <=65533 fits 16 bits.
 * Result r22..25 is nonnegative signed32. Only call-clobbered registers
 * r18..26 and flags change; r1 and all callee-saved registers are untouched.
 * No stack, hardware memory access or interrupt masking. C fallback in .h. */
.section .text.speex_wb_gain_div_avr,"ax",@progbits
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

/* Exact saturated LPC-response divide; see the .h for the caller domain.
 * n r22..25 = low*128 + ((int16_t)d>>1), d r18..21 = high >0.
 * n is -16256..43017855; d <=270414. A negative n implies d>=32768,
 * hence |n|<d and truncation gives zero. Otherwise take n>>15 first:
 * if it is >=d, saturation is certain; else only fifteen quotient bits
 * remain. A 24-bit remainder holds 2*d-1 <=540827 without overflow.
 * Return r24:25 in 0..32767. Only caller-clobbered registers and flags
 * change; no memory, stack, interrupt mask or r1 access. */
.section .text.speex_wb_ratio_div_avr,"ax",@progbits
.global speex_wb_ratio_div_avr
.type speex_wb_ratio_div_avr,@function
speex_wb_ratio_div_avr:
    sbrc r25,7
    rjmp .Lratio_zero
    movw r26,r24
    lsl r22
    rol r23
    rol r26
    rol r27
    clr r30
    cp r26,r18
    cpc r27,r19
    cpc r30,r20
    brsh .Lratio_saturated
    ldi r21,15
.Lratio_bit:
    lsl r22
    rol r23
    rol r26
    rol r27
    rol r30
    cp r26,r18
    cpc r27,r19
    cpc r30,r20
    brcs .Lratio_next
    sub r26,r18
    sbc r27,r19
    sbc r30,r20
    ori r22,1
.Lratio_next:
    dec r21
    brne .Lratio_bit
    movw r24,r22
    ret
.Lratio_saturated:
    ldi r24,255
    ldi r25,127
    ret
.Lratio_zero:
    clr r24
    clr r25
    ret
.size speex_wb_ratio_div_avr,.-speex_wb_ratio_div_avr

/* Positive finite HB1 domain only. Numerator r22..25, divisor r20:21.
 * n=a*128+(d>>1), a 1..335949, d 111..31849; numerator strictly positive.
 * Remainder <d<=31849 implies shifted remainder <=63697 fits 16 bits.
 * Unsaturated compare proves initial C=1; CP/CPC or SUB/SBC provides
 * the next inverse quotient bit. All registers are call-clobbered.
 * The separately selectable C reference is in wb_gain_div.h. */
.macro speex_hb_ratio_inverse_bit
    rol r22
    rol r23
    rol r26
    rol r27
    cp r26,r20
    cpc r27,r21
    brcs .Lhb_ratio_skip\@
    sub r26,r20
    sbc r27,r21
.Lhb_ratio_skip\@:
.endm
.section .text.speex_wb_ratio_hb_div_avr,"ax",@progbits
.global speex_wb_ratio_hb_div_avr
.type speex_wb_ratio_hb_div_avr,@function
speex_wb_ratio_hb_div_avr:
    movw r26,r24
    lsl r22
    rol r23
    rol r26
    rol r27
    cp r26,r20
    cpc r27,r21
    brlo .Lhb_ratio_small
    rjmp .Lhb_ratio_saturated
.Lhb_ratio_small:
    .rept 15
    speex_hb_ratio_inverse_bit
    .endr
    rol r22
    rol r23
    com r22
    com r23
    movw r24,r22
    ret
.Lhb_ratio_saturated:
    ldi r24,255
    ldi r25,127
    ret
.size speex_wb_ratio_hb_div_avr,.-speex_wb_ratio_hb_div_avr
.purgem speex_hb_ratio_inverse_bit
