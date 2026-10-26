/* Assembler include only; do not compile this file independently.
 * Original project Q14 arithmetic shared by GNU-ABI and fused-stage entries.
 * Enhanced AVR5, hardware MUL. a is the low register number of a signed16
 * operand (16 or 18); b enters r23:r20, result r25:r22. Clobbers r0/r1,
 * r20..27/Z, preserves a and r2..17/Y. Default bodies clear r1. The private
 * general-body clear_zero=0 form leaves r1 clobbered: its caller must not
 * consume it as zero or cross an ABI boundary before restoring it.
 * Neither body requires r1 zero on entry. No stack, IO or CLI.
 * General body requires signed30 b; aligned body also requires b%64==0.
 * The C equations remain in nb3_c_math.h; use speex_platform.h opt-in. */
#ifndef MICROMUSIC_Q14_ASM_MACROS
#define MICROMUSIC_Q14_ASM_MACROS

.macro SPEEX_LSP_Q14_BODY a,clear_zero=1

    movw r30, r22       /* original high word of b */
    clr r26             /* low product's temporary zero */
    /* Signed16 a times unsigned16 low b, exact signed32 result. */
    mulsu \a+1, r21
    movw r24, r0
    mul \a, r20
    movw r22, r0
    mulsu \a+1, r20
    sbc r25, r26
    add r23, r0
    adc r24, r1
    adc r25, r26
    mul \a, r21
    add r23, r0
    adc r24, r1
    adc r25, r26
    mov r26, r25
    lsl r26
    sbc r26, r26
    mov r27, r26
    movw r20, r30
    clr r30             /* high word moved; Z low is now a free zero */
    /* Add signed16 a * signed16 high b at product bit 16. */
    muls \a+1, r21
    add r26, r0
    adc r27, r1
    mul \a, r20
    add r24, r0
    adc r25, r1
    adc r26, r30
    adc r27, r30
    mulsu \a+1, r20
    sbc r27, r30
    add r25, r0
    adc r26, r1
    adc r27, r30
    mulsu r21, \a
    sbc r27, r30
    add r25, r0
    adc r26, r1
    adc r27, r30
    .rept 2
    lsl r23
    rol r24
    rol r25
    rol r26
    rol r27
    .endr
    movw r22, r24
    movw r24, r26
.if \clear_zero
    clr r1
.endif
.endm

.macro SPEEX_LSP_P1_BODY a

    .rept 2
    lsl r20
    rol r21
    rol r22
    rol r23
    .endr
    mov r30,r23
    mov r20,r21
    mov r21,r22
    clr r27
    mulsu \a+1,r21
    movw r24,r0
    mul \a,r20
    movw r22,r0
    mulsu \a+1,r20
    sbc r25,r27
    add r23,r0
    adc r24,r1
    adc r25,r27
    mul \a,r21
    add r23,r0
    adc r24,r1
    adc r25,r27
    mov r26,r25
    lsl r26
    sbc r26,r26
    mov r20,r30
    muls \a+1,r20
    add r25,r0
    adc r26,r1
    mulsu r20,\a
    sbc r26,r27
    add r24,r0
    adc r25,r1
    adc r26,r27
    mov r22,r23
    mov r23,r24
    mov r24,r25
    mov r25,r26
    clr r1
.endm

#endif
