/* Original project paired polynomial loop, AVR5 / ATmega328P / GNU ABI.
 * p r25:r24, q r23:r22, fp r21:r20, fq r19:r18. Arrays are disjoint;
 * each has n+2 int32 slots, p0=q0=2^20, p1/q1 divisible by 64, and
 * product inputs satisfy -2^29 <= b < 2^29. Preserve every Q14 floor
 * and modulo-32 update while descending through the original old words.
 * Save r2..r17/Y (18 bytes). The private first-pass and product returns
 * add 4 bytes at peak on this two-byte-PC target. r2 retains n, r3 counts
 * inner updates. T selects the private p return or final q epilogue.
 * General products preserve T and leave r1 scratch; the final aligned P1
 * product clears r1 before the p0 addition and both return boundaries.
 * No C call, static SRAM, IO or interrupt masking. IRQ handlers must
 * preserve interrupted r1 and SREG/T. Explicit C/architecture selection:
 * nb3_lsp_pair.h. Arithmetic derives from licensed Xiph Speex equations;
 * original vendor notices remain under vendor/speex-1.2.1. */
#include "lsp_stage_macros.S"
.section .text.speex_avr_lsp_pairs,"ax",@progbits
.global speex_avr_lsp_pair2
.type speex_avr_lsp_pair2,@function
speex_avr_lsp_pair2:
    ldi r26,2
    rjmp .Lpair_prologue
.size speex_avr_lsp_pair2,.-speex_avr_lsp_pair2
.global speex_avr_lsp_pair3
.type speex_avr_lsp_pair3,@function
speex_avr_lsp_pair3:
    ldi r26,3
    rjmp .Lpair_prologue
.size speex_avr_lsp_pair3,.-speex_avr_lsp_pair3
.global speex_avr_lsp_pair4
.type speex_avr_lsp_pair4,@function
speex_avr_lsp_pair4:
    ldi r26,4
.size speex_avr_lsp_pair4,.-speex_avr_lsp_pair4
 .type speex_lsp_pair_loop_private,@function
speex_lsp_pair_loop_private:
.Lpair_prologue:
.irp r,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push \r
.endr
    mov r2,r26
    movw r4,r22
    movw r6,r18
    movw r16,r20
    movw r28,r24
    clt
    rcall .Lpair_body
    movw r28,r4
    movw r16,r6
    set
    rjmp .Lpair_body
.Lpair_body:
    mov r3,r2
    lsl r3
    lsl r3
    add r28,r3
    adc r29,r1
    STAGE_LOAD 8,0
    sbiw r28,4
    STAGE_LOAD 12,0
    STAGE_PRODUCT 8
    STAGE_BOUNDARY 12,8
    mov r3,r2
    dec r3
    dec r3
    breq .Lpair_tail
.Lpair_inner:
    STAGE_PRODUCT 12
    sbiw r28,4
    STAGE_LOAD 18,0
    add r8,r18
    adc r9,r19
    adc r10,r20
    adc r11,r21
    sub r8,r22
    sbc r9,r23
    sbc r10,r24
    sbc r11,r25
    STAGE_STORE 8,8
    movw r8,r12
    movw r10,r14
    movw r12,r18
    movw r14,r20
    dec r3
    brne .Lpair_inner
.Lpair_tail:
    sbiw r28,4
    STAGE_TAIL2
    brts .Lpair_restore
    ret
.Lpair_restore:
.irp r,29,28,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2
    pop \r
.endr
    ret
.size speex_lsp_pair_loop_private,.-speex_lsp_pair_loop_private
STAGE_DEFINE_PRODUCT speex_lsp_pair_product_private
