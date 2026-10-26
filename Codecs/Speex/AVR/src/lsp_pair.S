/* Original project paired stages, classic AVR5/hardware MUL, GNU ABI.
 * p r25:24, q r23:22, fp r21:20, fq r19:18. Save r4..17/Y once;
 * retain q/fq in r4..7 across the first polynomial. Disjoint arrays,
 * p0/q0=2^20, p1/q1 divisible by64; signed30 inputs, signed16 roots.
 * The shared math body preserves T. CLT selects private RET after p;
 * SET selects the final restore/RET after q. T is call-clobbered scratch.
 * No C call, hardware IO or interrupt masking; both passes finish with
 * r1=0. Interrupt handlers must preserve interrupted r1 and SREG incl T.
 * Explicit C equations/selection: nb3_lsp_pair.h. Own saves16 + RCALL2 B. */
#include "lsp_stage_macros.S"
.section .text.speex_avr_lsp_pairs,"ax",@progbits
.macro PAIR_PROLOGUE
.irp r,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push \r
.endr
    movw r4,r22
    movw r6,r18
    movw r16,r20
    movw r28,r24
.endm
.global speex_avr_lsp_pair2
.type speex_avr_lsp_pair2,@function
speex_avr_lsp_pair2:
    PAIR_PROLOGUE
    clt
    rcall .Lpair_body2
    movw r28,r4
    movw r16,r6
    set
    rjmp .Lpair_body2
.size speex_avr_lsp_pair2,.-speex_avr_lsp_pair2
.global speex_avr_lsp_pair3
.type speex_avr_lsp_pair3,@function
speex_avr_lsp_pair3:
    PAIR_PROLOGUE
    clt
    rcall .Lpair_body3
    movw r28,r4
    movw r16,r6
    set
    rjmp .Lpair_body3
.size speex_avr_lsp_pair3,.-speex_avr_lsp_pair3
.global speex_avr_lsp_pair4
.type speex_avr_lsp_pair4,@function
speex_avr_lsp_pair4:
    PAIR_PROLOGUE
    clt
    rcall .Lpair_body4
    movw r28,r4
    movw r16,r6
    set
    rjmp .Lpair_body4
.size speex_avr_lsp_pair4,.-speex_avr_lsp_pair4
.Lpair_body2:
    STAGE_START2
    rjmp .Lpair_tail2
.Lpair_body3:
    STAGE_START3
    rjmp .Lpair_from3
.Lpair_body4:
    STAGE_START4
.Lpair_from3:
    STAGE_FROM3
.Lpair_tail2:
    STAGE_TAIL2
    brts .Lpair_restore
    ret
.Lpair_restore:
.irp r,29,28,17,16,15,14,13,12,11,10,9,8,7,6,5,4
    pop \r
.endr
    ret
