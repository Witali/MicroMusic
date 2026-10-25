/* UM88 AVR25 kernel. Equivalent selectable C in engine.c, no hardware I/O. */
#if defined(__AVR_ATtiny88__) && defined(UM_ENABLE_AVR_ASM) && UM_ENABLE_AVR_ASM
.text
/* GNU uint32_t result: signed left in r23:r22, right in r25:r24.
   Both pans are live even for mono so one kernel serves every composition. */
.global um_render
.type um_render,@function
um_render:
    push r14
    push r15
    push r16
    push r17
    clr r14
    clr r15
    clr r16
    clr r17
    clr r20
    ldi r26,lo8(um)
    ldi r27,hi8(um)
    lds r18,um+216
1:
    ld r24,X+
    ld r25,X+
    ld r30,X+
    ld r31,X+
    add r24,r30
    adc r25,r31
    sbiw r26,4
    st X+,r24
    st X+,r25
    adiw r26,2
    movw r30,r26
    swap r25
    andi r25,15
    add r30,r25
    adc r31,r1
    ld r24,Z
    adiw r26,18
    ld r19,X+
    cpi r19,128
    brne .Lmix_general
.Lmix_accumulate:
    clr r25
    sbrc r24,7
    com r25
    add r14,r24
    adc r15,r25
    add r16,r24
    adc r17,r25
.Lmix_next:
    dec r18
    breq 9f
    rjmp 1b
9:
    movw r22,r14
    movw r24,r16
    pop r17
    pop r16
    pop r15
    pop r14
    ret
.Lmix_general:
    sbrs r19,7
    rjmp .Lmix_group
    sbrs r19,5
    rjmp .Lmix_pan
.Lmix_group:
    add r20,r24
    sbrs r19,7
    rjmp .Lmix_next
    sbiw r26,3
    ld r25,X
    adiw r26,3
    swap r25
    andi r25,240
    ldi r30,lo8(um_amplitudes)
    ldi r31,hi8(um_amplitudes)
    add r30,r25
    adc r31,r1
    movw r22,r30
    mov r24,r20
    asr r24
    asr r24
    asr r24
    subi r24,248
    add r30,r24
    adc r31,r1
    lpm r24,Z
    movw r30,r22
    andi r20,7
    subi r20,248
    add r30,r20
    adc r31,r1
    lpm r25,Z
    lsr r25
    lsr r25
    lsr r25
    add r24,r25
    clr r20
    sbrc r19,0
    asr r24
.Lmix_pan:
    clr r25
    sbrc r24,7
    com r25
    movw r22,r24
    sbrs r19,3
    rjmp .Lleft_ready
    asr r23
    ror r22
.Lleft_ready:
    add r14,r22
    adc r15,r23
    sbrs r19,4
    rjmp .Lright_ready
    asr r25
    ror r24
.Lright_ready:
    add r16,r24
    adc r17,r25
    rjmp .Lmix_next
.size um_render,.-um_render

/* Cache one packed wave, preserving the C shift/rounding exactly. GNU ABI:
   source r25:r24, target r23:r22, level r20, gain r18. No callee-save use. */
.macro scale_nibble
    andi r22,15
    sbrc r18,5
    rjmp 1f
    ldi r30,lo8(um_amplitudes)
    ldi r31,hi8(um_amplitudes)
    add r30,r20
    adc r31,r1
    add r30,r22
    adc r31,r1
    lpm r22,Z
    rjmp 2f
1:
    subi r22,8
2:
    sbrs r18,2
    rjmp 3f
    asr r22
    asr r22
    asr r22
    asr r22
3:
    sbrs r18,1
    rjmp 4f
    asr r22
    asr r22
4:
    sbrc r18,0
    asr r22
    st X+,r22
.endm
.global um_scale_wave
.type um_scale_wave,@function
um_scale_wave:
    movw r26,r22
    swap r20
    andi r20,240
    ldi r19,8
5:
    movw r30,r24
    lpm r21,Z+
    movw r24,r30
    mov r22,r21
    scale_nibble
    swap r21
    mov r22,r21
    scale_nibble
    dec r19
    breq 6f
    rjmp 5b
6:
    ret
.size um_scale_wave,.-um_scale_wave
#endif
