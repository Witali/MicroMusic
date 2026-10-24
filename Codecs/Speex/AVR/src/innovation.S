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
#include "innovation_core.inc"
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
.Linnovation_packed_setup:
    movw r26, r22
.Linnovation_packed_sample:
    ld r13, X+
    ld r14, X+
    ld r15, X+
    rjmp .Linnovation_sample
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
    speex_nb3_long_dot
.Linnovation_sample:
    speex_nb3_innovation_transform
    dec r3
    breq .Linnovation_done
    brtc .Linnovation_packed_again
    rjmp .Linnovation_long_sample
.Linnovation_packed_again:
    rjmp .Linnovation_packed_sample
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


/* Four indexed vectors in one ABI call. out/history/indices/scale/gains use
 * r25:r24/r23:r22/r21:r20/r19:r16/r15:r14. Save the four RAM indices on
 * the stack, then consume them once. r9 counts remaining vectors.
 * History/gains/scale survive each vector. Other entries keep their shared
 * rolling/packed/scalar loop; both bodies use the same arithmetic macros.
 * indices 0..31; exc_10_32_table has 32 ten-byte signed Flash vectors. */
.global speex_avr_long_innovation40
.type speex_avr_long_innovation40,@function
speex_avr_long_innovation40:
    push r9
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
    movw r28,r24
    movw r30,r20
    adiw r30,4
    .rept 4
    ld r20,-Z
    push r20
    .endr
    clr r2
    ldi r20,4
    mov r9,r20
    ldi r20,32
    mov r8,r20
    movw r26,r14
    ld r10,X+
    ld r11,X+
    ld r12,X
    movw r26,r22
    ld r4,X+
    ld r5,X+
    ld r6,X+
    ld r7,X+
.Llong40_shape:
    pop r20
    ldi r21,10
    mul r20,r21
    ldi r30,lo8(exc_10_32_table)
    ldi r31,hi8(exc_10_32_table)
    add r30,r0
    adc r31,r1
    clr r1
    ldi r20,10
    mov r3,r20
.Llong40_sample:
    speex_nb3_long_dot
    speex_nb3_innovation_transform
    dec r3
    breq .Llong40_vector_done
    rjmp .Llong40_sample
.Llong40_vector_done:
    dec r9
    breq .Llong40_done
    rjmp .Llong40_shape
.Llong40_done:
    clr r1
    pop r29
    pop r28
    pop r15
    pop r14
    pop r13
    pop r12
    pop r11
    pop r10
    pop r7
    pop r6
    pop r5
    pop r4
    pop r8
    pop r3
    pop r2
    pop r9
    ret
.size speex_avr_long_innovation40,.-speex_avr_long_innovation40

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
.Lzero_innovation_bias_setup:
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

/* Runtime count in r16, 0..10. Preserve it before scale moves to r19:r16.
 * Keep the fixed-ten path and its timing unchanged. */
.global speex_avr_zero_innovation_n
.type speex_avr_zero_innovation_n, @function
speex_avr_zero_innovation_n:
    tst r16
    brne .Lzero_innovation_n_nonempty
    ret
.Lzero_innovation_n_nonempty:
    push r2
    push r3
    push r8
    push r16
    push r17
    push r28
    push r29
    mov r3, r16
    movw r28, r24
    movw r30, r22
    movw r16, r18
    movw r18, r20
    clr r2
    rjmp .Lzero_innovation_bias_setup
.size speex_avr_zero_innovation_n, .-speex_avr_zero_innovation_n
