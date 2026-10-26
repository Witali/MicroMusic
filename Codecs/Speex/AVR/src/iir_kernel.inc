/* Order 8/10, 40 samples, mirrored signed16 history and coefficient ages.
 * State = 6*IIR_ORDER zeroed bytes. Same ABI as speex_avr_iir40.
 * Exact modulo-32 arithmetic and transposed-filter coefficient transitions. */
.text
/* Source macros share the exact arithmetic without per-tap CALL overhead. */
.macro IIR_MAC coefficient, first=0
    .ifc \coefficient,memory
    ld r18, X+
    ld r19, X+
    .else
    movw r18, \coefficient
    .endif
    ld r21, -Z
    ld r20, -Z
    /* Signed 16x16: initialize the accumulator on the first tap; later
     * taps use AVR201 method B addition modulo 2^32. No zeroing pass. */
    muls r19, r21
    .if \first
    movw r24, r0
    mul r18, r20
    movw r22, r0
    .else
    movw r4, r0
    mul r18, r20
    add r22, r0
    adc r23, r1
    adc r24, r4
    adc r25, r5
    .endif
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
.endm
.macro IIR_FINISH age
    /* PSHR32(sum,13), preserving wrap when adding the rounding bias. */
    add r23,r3
    adc r24, r2
    adc r25, r2
    lsl r23
    rol r24
    rol r25
    sbc r22, r22
    .rept 2
    lsl r23
    rol r24
    rol r25
    rol r22
    .endr
    mov r0, r22
    movw r22, r24
    mov r24, r0
    /* Rounded signed32 >>13 lies in [-262144,262143]. Adding signed16
     * input lies in [-294912,294910], so signed24 is sufficient. */
    /* Add sign-extended input before saturation. Read before writing y so
     * the upstream in-place x==y case is supported. */
    movw r30, r6
    ld r18, Z+
    ld r19, Z+
    movw r6, r30
    mov r20, r19
    lsl r20
    sbc r20, r20
    add r22, r18
    adc r23, r19
    adc r24, r20
    tst r24
    brmi .Lnegative\@
    brne .Lclip_positive\@
    sbrs r23, 7
    rjmp .Lstore\@
.Lclip_positive\@:
    ldi r22, 255
    ldi r23, 127
    rjmp .Lstore\@
.Lnegative\@:
    cpi r24, 255
    brne .Lclip_negative\@
    sbrs r23, 7
    rjmp .Lclip_negative\@
    cpi r23, 128
    brne .Lstore\@
    tst r22
    brne .Lstore\@
.Lclip_negative\@:
    ldi r22, 1
    ldi r23, 128
.Lstore\@:
    movw r30, r8
    st Z+, r22
    st Z+, r23
    movw r8, r30
    com r22
    com r23
    subi r22, 255
    sbci r23, 255
    /* Y advances to the next sample without a separate address calculation.
     * Mirror/age offsets compensate for the two postincrements. */
    st Y+,r22
    st Y+,r23
    std Y+(2*IIR_ORDER-2),r22
    std Y+(2*IIR_ORDER-1),r23
    /* Sample 0 uses all previous coefficients; sample 1 uses new den[0],
     * etc. The transposed recurrence ages coefficients in exactly this way. */
    .if \age
    movw r26, r10
    ld r18, X+
    ld r19, X+
    movw r10, r26
    std Y+(4*IIR_ORDER-2),r18
    std Y+(4*IIR_ORDER-1),r19
    .endif
    cp r28,r16
    brne .Lcursor_done\@
    .if \age
    movw r28,r12
    .else
    sbiw r28,2*IIR_ORDER
    .endif
.Lcursor_done\@:
.endm
.global IIR_ENTRY
.type IIR_ENTRY, @function
IIR_ENTRY:
    push r2
    push r3
    push r4
    push r5
    push r6
    push r7
    push r8
    push r9
    push r10
    push r11
    push r12
    push r13
    push r14
    push r15
    push r16
    push r17
    push r28
    push r29
    movw r6, r24
    movw r10, r22
    movw r8, r20
    movw r12, r18
    movw r28,r18
    movw r14, r18
    ldi r24, 4*IIR_ORDER
    add r14, r24
    adc r15, r1
    clr r2
    /* One rounding constant for the whole block; r3 survives every MAC. */
    ldi r18,16
    mov r3,r18
    /* Y traverses 2*order bytes: its low end byte is reached only after
     * order words, including when the history crosses a 256-byte page. */
    mov r16,r12
    subi r16,-2*IIR_ORDER
    ldi r17, IIR_ORDER
.Lwarm_sample:
    movw r26, r14
    movw r30, r28
    adiw r30, 2*IIR_ORDER
    IIR_MAC memory,1
    .rept IIR_ORDER-1
    IIR_MAC memory
    .endr
    IIR_FINISH 1
    dec r17
    breq .Lsteady_setup
    rjmp .Lwarm_sample
.Lsteady_setup:
    /* Age updates are complete. X ends every steady dot product at the
     * coefficient-table end, so rewind it by a fixed displacement instead
     * of rebuilding it from the state base. Reuse that now-dead base pair
     * for a third LPC word; rewind Y at wrap as well. No extra SRAM. */
    movw r26, r14
    ld r10, X+
    ld r11, X+
    ld r14, X+
    ld r15, X+
    ld r12, X+
    ld r13, X+
    adiw r26,2*(IIR_ORDER-3)
    ldi r17, 40-IIR_ORDER
.Lsteady_sample:
    sbiw r26,2*(IIR_ORDER-3)
    movw r30, r28
    adiw r30, 2*IIR_ORDER
    IIR_MAC r10,1
    IIR_MAC r14
    IIR_MAC r12
    .rept IIR_ORDER-3
    IIR_MAC memory
    .endr
    IIR_FINISH 0
    dec r17
    breq .Ldone
    rjmp .Lsteady_sample
.Ldone:
    clr r1
    pop r29
    pop r28
    pop r17
    pop r16
    pop r15
    pop r14
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop r7
    pop r6
    pop r5
    pop r4
    pop r3
    pop r2
    ret
.size IIR_ENTRY, .-IIR_ENTRY
