/* Order 8/10, 40 samples, mirrored signed16 history and coefficient ages.
 * State = 6*IIR_ORDER zeroed bytes. Same ABI as speex_avr_iir40.
 * Exact modulo-32 arithmetic and transposed-filter coefficient transitions. */
#if IIR_ORDER != 8 && IIR_ORDER != 10
#error This private 40-sample kernel supports orders 8 and 10
#endif
/* r3 counts samples. After warm-up r16:r17 holds the first coefficient;
 * r10:r11, r14:r15 and r12:r13 hold the next three. Private group CALL/RET
 * adds two stack bytes on ATmega328P. r1 may remain dirty across a private
 * RET; no C call occurs there, and the external ABI return clears r1. */
.text
/* Source macros share the exact arithmetic without per-tap CALL overhead. */
.macro IIR_MAC coefficient, first=0, lo=18, hi=19
    .ifc \coefficient,memory
    ld r\lo, X+
    ld r\hi, X+
    .else
    .ifc \coefficient,r16
    .if \lo-16
    .error "Direct MAC expects r16:r17"
    .endif
    .if \hi-17
    .error "Direct MAC expects r16:r17"
    .endif
    .else
    movw r\lo, \coefficient
    .endif
    .endif
    ld r21, -Z
    ld r20, -Z
    /* Signed 16x16: initialize the accumulator on the first tap; later
     * taps use AVR201 method B addition modulo 2^32. No zeroing pass. */
    muls r\hi, r21
    .if \first
    movw r24, r0
    mul r\lo, r20
    movw r22, r0
    .else
    movw r4, r0
    mul r\lo, r20
    add r22, r0
    adc r23, r1
    adc r24, r4
    adc r25, r5
    .endif
    mulsu r\hi, r20
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
    mulsu r21, r\lo
    sbc r25, r2
    add r23, r0
    adc r24, r1
    adc r25, r2
.endm
.macro IIR_FINISH age
    /* PSHR32(sum,13), preserving wrap when adding the rounding bias. */
    subi r23,lo8(-16)
    sbci r24,255
    sbci r25,255
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
    /* NEG sets C iff the original low byte was nonzero. The high-byte
     * subtract therefore supplies the exact two's-complement carry. */
    com r23
    neg r22
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
    /* Exactly order warm samples update all coefficient ages. Y wraps
     * once after the phase, so no per-sample cursor test is needed. */
    ldi r18,IIR_ORDER
    mov r3,r18
.Lwarm_sample:
    movw r26, r14
    movw r30, r28
    adiw r30, 2*IIR_ORDER
    IIR_MAC memory,1
    .rept IIR_ORDER-1
    IIR_MAC memory
    .endr
    IIR_FINISH 1
    dec r3
    breq .Lsteady_setup
    rjmp .Lwarm_sample
.Lsteady_setup:
    movw r28,r12
    /* Ages are now fixed. Immediate rounding frees r3 for the counter;
     * group-boundary Y resets free r16:r17 for a fourth cached word. The
     * first coefficient can feed MULSU directly from that high-register
     * pair; the other three use MOVW. X still uses a fixed rewind. */
    movw r26, r14
    ld r16, X+
    ld r17, X+
    ld r10, X+
    ld r11, X+
    ld r14, X+
    ld r15, X+
    ld r12, X+
    ld r13, X+
    adiw r26,2*(IIR_ORDER-4)
    .rept 40/IIR_ORDER-1
    rcall .Liir_group
    .endr
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

/* A group consumes exactly one mirrored-history revolution. Reusing this
 * body avoids duplicating the dot product and removes every cursor test. */
.Liir_group:
    ldi r18,IIR_ORDER
    mov r3,r18
.Lsteady_sample:
    sbiw r26,2*(IIR_ORDER-4)
    movw r30, r28
    adiw r30, 2*IIR_ORDER
    IIR_MAC r16,1,16,17
    IIR_MAC r10
    IIR_MAC r14
    IIR_MAC r12
    .rept IIR_ORDER-4
    IIR_MAC memory
    .endr
    IIR_FINISH 0
    dec r3
    breq .Lgroup_done
    rjmp .Lsteady_sample
.Lgroup_done:
    sbiw r28,2*IIR_ORDER
    ret
.size IIR_ENTRY, .-IIR_ENTRY
