/* in-place 40 samples: t=floor(.9*x), v=low16((t*g+256)>>9),
 * alternating sign. Exact rounded HB1 excitation without a 32-bit buffer. */
.text
.global speex_wb_fold40_avr
.type speex_wb_fold40_avr,@function
speex_wb_fold40_avr:
    .irp reg,2,4,5,6,7,8,9,10,11,16
    push r\reg
    .endr
    movw r26,r24
    movw r4,r20
    movw r6,r22
    clr r2
    ldi r16,40
.Lfold:
    ld r20,X+
    ld r21,X
    sbiw r26,1
    ldi r18,51
    ldi r19,115
    muls r19,r21
    movw r10,r0
    mul r18,r20
    movw r8,r0
    mulsu r19,r20
    sbc r11,r2
    add r9,r0
    adc r10,r1
    adc r11,r2
    mulsu r21,r18
    sbc r11,r2
    add r9,r0
    adc r10,r1
    adc r11,r2
    lsl r9
    rol r10
    rol r11
    movw r20,r10
    mul r20,r4
    movw r8,r0
    clr r10
    clr r11
    mul r21,r4
    add r9,r0
    adc r10,r1
    adc r11,r2
    mul r20,r5
    add r9,r0
    adc r10,r1
    adc r11,r2
    mul r21,r5
    add r10,r0
    adc r11,r1
    mul r20,r6
    add r10,r0
    adc r11,r1
    mul r21,r6
    add r11,r0
    mul r20,r7
    add r11,r0
    sbrs r21,7
    rjmp .Lpositive
    sub r10,r4
    sbc r11,r5
.Lpositive:
    ldi r18,1
    add r9,r18
    adc r10,r2
    adc r11,r2
    lsr r11
    ror r10
    ror r9
    sbrs r16,0
    rjmp .Lstore
    com r9
    com r10
    add r9,r18
    adc r10,r2
.Lstore:
    st X+,r9
    st X+,r10
    dec r16
    breq .Ldone
    rjmp .Lfold
.Ldone:
    clr r1
    .irp reg,16,11,10,9,8,7,6,5,4,2
    pop r\reg
    .endr
    ret
.size speex_wb_fold40_avr,.-speex_wb_fold40_avr
