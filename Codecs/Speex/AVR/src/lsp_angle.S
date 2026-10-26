/* Exact ANGLE2X leaf, classic AVR5/MUL, GNU ABI. x/result r25:24.
 * Call-clobbered registers only, own stack0, no explicit data-memory or hardware IO.
 * Original P13 rounding/casts survive. r22 stays zero; MUL's r1 is
 * private until the external RET. T retains the reflected-half flag.
 * All MULSU operands stay in r16..23. Full signed16 inputs; C equations
 * and selector: nb3_lsp_angle.h. y r19:18, coefficient r21:20. */
.macro ANGLE_WORD_BIAS bias,dest=20
    subi r25,lo8(-((\bias)>>8))
    sbci r26,hi8(-((\bias)>>8))
    sbci r27,hlo8(-((\bias)>>8))
    .rept 3
    lsl r25
    rol r26
    rol r27
    .endr
    movw \dest,r26
.endm
.section .text.speex_avr_lsp_angle,"ax",@progbits
.global speex_avr_lsp_angle
.type speex_avr_lsp_angle,@function
speex_avr_lsp_angle:
    cpi r24,lo8(12868)
    ldi r18,hi8(12868)
    cpc r25,r18
    clt
    brlt .Langle_folded
    set
    ldi r18,lo8(25736)
    ldi r19,hi8(25736)
    sub r18,r24
    sbc r19,r25
    movw r24,r18
.Langle_folded:
    movw r18,r24
    clr r22
    /* Three-MUL signed square; double the cross term in 17 bits. */
    muls r19,r19
    movw r26,r0
    mul r18,r18
    movw r24,r0
    mulsu r19,r18
    sbc r23,r23
    lsl r0
    rol r1
    rol r23
    add r25,r0
    adc r26,r1
    adc r27,r23
    ANGLE_WORD_BIAS 4096,18
    /* a=340+P13(-10*y), always 300..380 for signed16 y.
     * Only product bits13..20 are needed; its result high byte is 1. */
    ldi r20,lo8(-10)
    mulsu r20,r18
    movw r24,r0
    sbc r26,r26
    muls r20,r19
    add r25,r0
    adc r26,r1
    subi r25,lo8(-(0x2a9000>>8))
    sbci r26,hi8(-(0x2a9000>>8))
    .rept 3
    lsl r25
    rol r26
    .endr
    mov r20,r26
    ldi r21,1
    /* y*(256+a_low): two MULs plus an exact signed y<<8. */
    mul r18,r20
    movw r24,r0
    mulsu r19,r20
    sbc r27,r27
    mov r26,r1
    add r25,r0
    adc r26,r22
    adc r27,r22
    sbrc r19,7
    dec r27
    add r25,r18
    adc r26,r19
    adc r27,r22
    ANGLE_WORD_BIAS 0xfe001000
    /* Final full signed16 product. */
    muls r19,r21
    movw r26,r0
    mul r18,r20
    movw r24,r0
    mulsu r19,r20
    sbc r27,r22
    add r25,r0
    adc r26,r1
    adc r27,r22
    mulsu r21,r18
    sbc r27,r22
    add r25,r0
    adc r26,r1
    adc r27,r22
    /* K1 enters the bias. Extract bits11..26 then clear the two bits
     * discarded by original P13 before its final word shift by two. */
    subi r25,lo8(-(0x04001000>>8))
    sbci r26,hi8(-(0x04001000>>8))
    sbci r27,hlo8(-(0x04001000>>8))
    .rept 3
    lsr r27
    ror r26
    ror r25
    .endr
    andi r25,252
    mov r24,r25
    mov r25,r26
    brtc .Langle_done
    /* NEG low supplies the exact high-byte carry, including low == 0. */
    com r25
    neg r24
    sbci r25,255
.Langle_done:
    clr r1
    ret
.size speex_avr_lsp_angle,.-speex_avr_lsp_angle
