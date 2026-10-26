/* UM88 AVR25 kernel. Equivalent selectable C in engine.c, no hardware I/O. */
#include "audio-channels.h"
#if defined(__AVR_ATtiny88__) && defined(UM_ENABLE_AVR_ASM) && UM_ENABLE_AVR_ASM
.text
/* GNU ABI: mono int16_t left in r25:r24; stereo uint32_t packs signed left
   in r23:r22 and right in r25:r24. Only the selected accumulators are live. */
.global um_render
.type um_render,@function
um_render:
    push r14
    push r15
#if UM_OUTPUT_CHANNELS == 2
    push r16
    push r17
#endif
    clr r14
    clr r15
#if UM_OUTPUT_CHANNELS == 2
    clr r16
    clr r17
#endif
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
#if UM_OUTPUT_CHANNELS == 2
    add r16,r24
    adc r17,r25
#endif
.Lmix_next:
    dec r18
    breq 9f
    rjmp 1b
9:
#if UM_OUTPUT_CHANNELS == 1
    movw r24,r14
#else
    movw r22,r14
    movw r24,r16
    pop r17
    pop r16
#endif
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
    ld r21,X
    adiw r26,3
    mov r24,r20
    clr r25
    sbrc r24,7
    com r25
    clr r22
    clr r23
    /* Four level bits; Z is caller-clobbered and dead after the wave read. */
    ldi r30,4
.Lgain_loop:
    lsr r21
    brcc .Lgain_skip
    add r22,r24
    adc r23,r25
.Lgain_skip:
    lsl r24
    rol r25
    dec r30
    brne .Lgain_loop
    asr r23
    ror r22
    asr r23
    ror r22
    asr r23
    ror r22
    mov r24,r22
    clr r20
    sbrc r19,0
    asr r24
.Lmix_pan:
    clr r25
    sbrc r24,7
    com r25
#if UM_OUTPUT_CHANNELS == 1
    sbrs r19,3
    rjmp .Lleft_ready
    asr r25
    ror r24
.Lleft_ready:
    add r14,r24
    adc r15,r25
#else
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
#endif
    rjmp .Lmix_next
.size um_render,.-um_render

/* Cache one packed wave, preserving the C shift/rounding exactly. GNU ABI:
   source r25:r24, target r23:r22, level r20, gain r18. No callee-save use. */
.macro scale_nibble
    andi r22,15
    subi r22,8
    sbrc r18,5
    rjmp 2f
    mov r23,r22
    clr r22
    /* Preserve level in r20 and the Flash cursor in r25:r24. */
    mov r30,r20
    ldi r31,4
7:
    lsr r30
    brcc 8f
    add r22,r23
8:
    lsl r23
    dec r31
    brne 7b
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
