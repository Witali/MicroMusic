/* Original ATmega328P NB3 vector kernel, 10 signed Flash shapes.
 * void speex_avr_innovation10(int16_t *out, const uint8_t *pitch24,
 *                            const int8_t *shape_flash, int32_t scale);
 * ABI: out r25:r24, pitch r23:r22, shape r21:r20, scale r19:r16.
 * NB3 scale is positive and <=121000000; shape*scale >>12 fits signed32.
 * floor(shape*scale/256) is formed with four signed 8x8 products, then
 * clearing its low nibble and shifting left 3 gives (shape*scale>>12)<<7.
 * This is exactly upstream MULT16_32_Q14(shape*4,scale)<<7 for this bound.
 * Read packed unscaled pitch, clamp +/-2048000 and insert a zero low byte
 * to form the original sanitized pitch*2. Round >>14 and saturate +/-32767.
 * Second entry fuses three signed8 gains and a rolling signed16 history:
 * void speex_avr_long_innovation10(int16_t *out,const int16_t *history,
 *     const int8_t *shape_flash,int32_t scale,const int8_t *gains_ram);
 * Additional ABI arg: gains r15:r14. Twelve history samples, three gains;
 * L1(gains)<=147 keeps every prefix/product sum in signed24.
 * Shared innovation/clamp body: T=0 packed pitch, T=1 rolling history.
 * GCC ISRs preserve SREG.T. All callee-saved registers and r1 restored;
 * scale registers remain read-only and interrupts remain enabled. */
.text
.global speex_avr_innovation10
.type speex_avr_innovation10, @function
speex_avr_innovation10:
    push r2
    push r3
    push r8
    push r13
    push r14
    push r15
    push r28
    push r29
    clt
    rjmp .Linnovation_setup
.global speex_avr_long_innovation10
.type speex_avr_long_innovation10, @function
speex_avr_long_innovation10:
    push r2
    push r3
    push r8
    push r4
    push r5
    push r6
    push r7
    push r10
    push r11
    push r12
    push r13
    push r14
    push r15
    push r28
    push r29
    set
.Linnovation_setup:
    movw r28, r24
    movw r30, r20
    clr r2
    ldi r20, 10
    mov r3, r20
.Linnovation_bias_setup:
    ldi r20, 32
    mov r8, r20
    brts .Linnovation_long_setup
    rjmp .Linnovation_packed_setup
.Linnovation_long_setup:
    movw r26, r14
    ld r10, X+
    ld r11, X+
    ld r12, X
    movw r26, r22
    ld r4, X+
    ld r5, X+
    ld r6, X+
    ld r7, X+
.Linnovation_long_sample:
    /* A signed8 gain times a signed16 word, in r25:r23. */
    .macro long_product lo, hi, gain
    mov r20, \gain
    mov r21, \hi
    muls r21, r20
    movw r24, r0
    mov r21, \lo
    mulsu r20, r21
    mov r23, r0
    sbc r25, r2
    add r24, r1
    adc r25, r2
    .endm
    long_product r4,r5,r10
    movw r14, r24
    mov r13, r23
    long_product r6,r7,r11
    add r13, r23
    adc r14, r24
    adc r15, r25
    /* a is dead after its product; b is dead after the second product.
     * Advance the window before the final MAC and load c directly into b. */
    movw r4, r6
    ld r6, X+
    ld r7, X+
    long_product r6,r7,r12
    add r13, r23
    adc r14, r24
    adc r15, r25
    rjmp .Linnovation_sample
.Linnovation_packed_setup:
    movw r26, r22
.Linnovation_packed_sample:
    ld r13, X+
    ld r14, X+
    ld r15, X+
.Linnovation_sample:
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
    andi r22, 240
    .rept 3
    lsl r22
    rol r23
    rol r24
    rol r25
    .endr
    /* Clamp signed24 to +/-2048000 (0x1f4000 / 0xe0c000).
     * Compare signed high bytes first; only boundary bytes need lower tests. */
    ldi r20, 31
    cp r20, r15
    brlt .Lpitch_clip_positive
    brne .Lpitch_check_lower
    ldi r20, 64
    cp r20, r14
    brlo .Lpitch_clip_positive
    brne .Lpitch_ready
    tst r13
    brne .Lpitch_clip_positive
    rjmp .Lpitch_ready
.Lpitch_check_lower:
    ldi r20, 224
    cp r15, r20
    brlt .Lpitch_clip_negative
    brne .Lpitch_ready
    ldi r20, 192
    cp r14, r20
    brlo .Lpitch_clip_negative
    rjmp .Lpitch_ready
.Lpitch_clip_positive:
    mov r13, r2
    ldi r20, 64
    mov r14, r20
    ldi r20, 31
    mov r15, r20
    rjmp .Lpitch_ready
.Lpitch_clip_negative:
    mov r13, r2
    ldi r20, 192
    mov r14, r20
    ldi r20, 224
    mov r15, r20
.Lpitch_ready:
    /* pitch*2*128 has a zero low byte. The lower innovation byte stays
     * unchanged, and ADD (not ADC) starts the upper-byte carry chain. */
    add r23, r13
    adc r24, r14
    adc r25, r15
    add r23, r8
    adc r24, r2
    adc r25, r2
    /* Arithmetic >>14 through left alignment and carry. */
    lsl r23
    rol r24
    rol r25
    sbc r22, r22
    lsl r23
    rol r24
    rol r25
    rol r22
    mov r0, r22
    mov r22, r24
    mov r23, r25
    mov r24, r0
    /* Rounded wrapped signed32 >>14 fits signed18; do not materialize
     * a fourth sign-extension byte merely to saturate the result to s16. */
    tst r24
    brmi .Linnovation_negative
    brne .Linnovation_clip_positive
    sbrs r23, 7
    rjmp .Linnovation_store
.Linnovation_clip_positive:
    ldi r22, 255
    ldi r23, 127
    rjmp .Linnovation_store
.Linnovation_negative:
    cpi r24, 255
    brne .Linnovation_clip_negative
    sbrs r23, 7
    rjmp .Linnovation_clip_negative
    cpi r23, 128
    brne .Linnovation_store
    tst r22
    brne .Linnovation_store
.Linnovation_clip_negative:
    ldi r22, 1
    ldi r23, 128
.Linnovation_store:
    st Y+, r22
    st Y+, r23
    dec r3
    breq .Linnovation_done
    brts .Linnovation_long_again
    rjmp .Linnovation_packed_sample
.Linnovation_long_again:
    rjmp .Linnovation_long_sample
.Linnovation_done:
    clr r1
    pop r29
    pop r28
    pop r15
    pop r14
    pop r13
    brtc .Linnovation_restore_common
    pop r12
    pop r11
    pop r10
    pop r7
    pop r6
    pop r5
    pop r4
.Linnovation_restore_common:
    pop r8
    pop r3
    pop r2
    ret
.size speex_avr_innovation10, .-speex_avr_innovation10
.size speex_avr_long_innovation10, .-speex_avr_long_innovation10

/* Runtime count in r12, 0..10; retain the fixed-ten entry unchanged. */
.global speex_avr_long_innovation_n
.type speex_avr_long_innovation_n, @function
speex_avr_long_innovation_n:
    tst r12
    brne .Linnovation_n_nonempty
    ret
.Linnovation_n_nonempty:
    push r2
    push r3
    push r8
    push r4
    push r5
    push r6
    push r7
    push r10
    push r11
    push r12
    push r13
    push r14
    push r15
    push r28
    push r29
    movw r28, r24
    movw r30, r20
    clr r2
    mov r3, r12
    set
    rjmp .Linnovation_bias_setup
.size speex_avr_long_innovation_n, .-speex_avr_long_innovation_n


/* Scalar entry: three RAM words, then the unchanged common transform.
 * Same five arguments as the fixed-ten entry. Preserve the Flash pointer
 * in already-saved r3/r8 until the products are complete. */
.global speex_avr_long_innovation1
.type speex_avr_long_innovation1, @function
speex_avr_long_innovation1:
    push r2
    push r3
    push r8
    push r13
    push r14
    push r15
    push r28
    push r29
    movw r28, r24
    mov r3, r20
    mov r8, r21
    movw r26, r22
    movw r30, r14
    clr r2
    .macro scalar_product
    ld r20, Z+
    ld r22, X+
    ld r21, X+
    muls r21, r20
    movw r24, r0
    mov r21, r22
    mulsu r20, r21
    mov r23, r0
    sbc r25, r2
    add r24, r1
    adc r25, r2
    .endm
    scalar_product
    movw r14, r24
    mov r13, r23
    scalar_product
    add r13, r23
    adc r14, r24
    adc r15, r25
    scalar_product
    add r13, r23
    adc r14, r24
    adc r15, r25
    mov r30, r3
    mov r31, r8
    ldi r20, 1
    mov r3, r20
    ldi r20, 32
    mov r8, r20
    clt
    rjmp .Linnovation_sample
.size speex_avr_long_innovation1, .-speex_avr_long_innovation1


/* Zero adaptive sum only. ABI out r25:r24, Flash shape r23:r22,
 * nonnegative scale<=121000000 in r21:r18. Exact rounded output fits s16:
 * floor((shape*scale+262144)/524288). First form floor(product/256),
 * add 1024 and shift eleven. No pitch read/clamp or final saturation. */
.global speex_avr_zero_innovation10
.type speex_avr_zero_innovation10, @function
speex_avr_zero_innovation10:
    push r2
    push r3
    push r8
    push r16
    push r17
    push r28
    push r29
    movw r28, r24
    movw r30, r22
    movw r16, r18
    movw r18, r20
    clr r2
    ldi r20, 10
    mov r3, r20
    ldi r20, 4
    mov r8, r20
.Lzero_innovation_sample:
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
    add r23, r8
    adc r24, r2
    adc r25, r2
    .rept 3
    asr r25
    ror r24
    ror r23
    .endr
    st Y+, r23
    st Y+, r24
    dec r3
    brne .Lzero_innovation_sample
    clr r1
    pop r29
    pop r28
    pop r17
    pop r16
    pop r8
    pop r3
    pop r2
    ret
.size speex_avr_zero_innovation10, .-speex_avr_zero_innovation10
