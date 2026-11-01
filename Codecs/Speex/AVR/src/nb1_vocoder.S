/* Exact NB1 forty-word loop, ATmega328P/AVR5, GNU ABI.
 * out=r24:25, classes=r22:23, context=r20:21, cursor=r18:19.
 * Context/classes are read-only, cursor layout is checked by nb1_vocoder.h.
 * Countdown phase replaces the index comparison without changing pulses.
 * Mean stays in registers and shares the scalar exact arithmetic macro.
 * Saves all used callee registers; r1 cleared; interrupts remain enabled.
 * Explicit portable implementation: nb1_vocoder.c. */
#include "nb1_cache_layout.h"
#include "lowrate_mean_kernel.inc"
#if SPEEX_ENABLE_NB1 && SPEEX_ENABLE_WB1
.text
.global speex_nb1_synthesize40_avr
.type speex_nb1_synthesize40_avr,@function
speex_nb1_synthesize40_avr:
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
    push r18
    push r19
    movw r26,r24
    movw r28,r22
    movw r2,r20
    movw r30,r18
    ldd r4,Z+SPEEX_NB1_CURSOR_PULSE
    ldd r5,Z+(SPEEX_NB1_CURSOR_PULSE+1)
    ldd r6,Z+SPEEX_NB1_CURSOR_NOISE
    ldd r7,Z+(SPEEX_NB1_CURSOR_NOISE+1)
    ldd r14,Z+SPEEX_NB1_CURSOR_MEAN
    ldd r15,Z+(SPEEX_NB1_CURSOR_MEAN+1)
    ldd r17,Z+SPEEX_NB1_CURSOR_PHASE
    movw r30,r2
    ldd r8,Z+(2*SPEEX_NB1_PULSE_NOW)
    ldd r9,Z+(2*SPEEX_NB1_PULSE_NOW+1)
    ldd r10,Z+(2*SPEEX_NB1_PULSE_PREVIOUS)
    ldd r11,Z+(2*SPEEX_NB1_PULSE_PREVIOUS+1)
    ldd r16,Z+(2*SPEEX_NB1_PITCH)
    ldi r20,40
.Lnb1_sample:
    ld r18,Y+
    lsl r18
    movw r30,r2
    add r30,r18
    adc r31,r1
    ld r12,Z+
    ld r13,Z
    adiw r30,9
    ld r24,Z+
    ld r25,Z
    add r12,r4
    adc r13,r5
    sub r12,r6
    sbc r13,r7
    movw r6,r24
    clr r4
    clr r5
    tst r17
    brne .Lnb1_no_pulse
    add r12,r8
    adc r13,r9
    movw r4,r10
    mov r17,r16
.Lnb1_no_pulse:
    dec r17
    movw r22,r12
    SPEEX_NB1_MEAN r14,r15,r24,r25
    sub r12,r14
    sbc r13,r15
    st X+,r12
    st X+,r13
    dec r20
    breq .Lnb1_done
    rjmp .Lnb1_sample
.Lnb1_done:
    pop r31
    pop r30
    std Z+SPEEX_NB1_CURSOR_PULSE,r4
    std Z+(SPEEX_NB1_CURSOR_PULSE+1),r5
    std Z+SPEEX_NB1_CURSOR_NOISE,r6
    std Z+(SPEEX_NB1_CURSOR_NOISE+1),r7
    std Z+SPEEX_NB1_CURSOR_MEAN,r14
    std Z+(SPEEX_NB1_CURSOR_MEAN+1),r15
    std Z+SPEEX_NB1_CURSOR_PHASE,r17
    ld r18,-Y
    std Z+SPEEX_NB1_CURSOR_LAST,r18
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
.size speex_nb1_synthesize40_avr,.-speex_nb1_synthesize40_avr
#endif
