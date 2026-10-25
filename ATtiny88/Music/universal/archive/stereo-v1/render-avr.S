/* UM88 AVR25 kernel. Equivalent selectable C in engine.c, no hardware I/O. */
#if defined(__AVR_ATtiny88__) && defined(UM_ENABLE_AVR_ASM) && UM_ENABLE_AVR_ASM
.text
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
    clr r21
    clr r22
    clr r23
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
    sbrs r19,7
    rjmp 8f
    sbrs r19,5
    rjmp 7f
8:
    add r20,r24
    sbrs r19,7
    rjmp 4f
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
7:
    clr r25
    sbrc r24,7
    com r25
    movw r22,r24
    sbrs r19,3
    rjmp 5f
    asr r23
    ror r22
5:
    add r14,r22
    adc r15,r23
    sbrs r19,4
    rjmp 6f
    asr r25
    ror r24
6:
    add r16,r24
    adc r17,r25
4:
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
.size um_render,.-um_render
#endif
