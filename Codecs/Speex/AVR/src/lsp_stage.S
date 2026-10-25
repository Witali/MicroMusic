/* Original project kernels: constant stages 2/3/4, enhanced AVR5/GNU ABI.
 * p r25:r24, f r23:r22. p0=2^20, p1 divisible by 64; each product input
 * is signed30. Polynomial/root bounds and the selectable C implementation
 * are in nb3_lsp_stage.h. Read p[stage..1] once, write p[stage+1..1].
 * The stages share their descending tail. Twelve saved bytes (r8..17/Y),
 * no extra RAM, hardware IO or interrupt masking; preserve ABI and clear r1.
 * Q14 macro arithmetic matches the existing value kernels byte-for-byte;
 * independent rounding and wrap occur at each original product/update. */
#include "q14_macros.S"
.section .text.speex_avr_lsp_stages,"ax",@progbits
.macro STAGE_LOAD base,offset
    ldd \base,Y+\offset
    ldd \base+1,Y+\offset+1
    ldd \base+2,Y+\offset+2
    ldd \base+3,Y+\offset+3
.endm
.macro STAGE_STORE base,offset
    std Y+\offset,\base
    std Y+\offset+1,\base+1
    std Y+\offset+2,\base+2
    std Y+\offset+3,\base+3
.endm
.macro STAGE_PRODUCT base,p1=0
    movw r20,\base
    movw r22,\base+2
.if \p1
    STAGE_P1
.else
    STAGE_Q14
.endif
.endm
.macro STAGE_BOUNDARY base,offset
    movw r18,\base
    movw r20,\base+2
    lsl r18
    rol r19
    rol r20
    rol r21
    sub r18,r22
    sbc r19,r23
    sbc r20,r24
    sbc r21,r25
    STAGE_STORE 18,\offset
.endm
.macro STAGE_INNER current,offset
    add \current,r18
    adc \current+1,r19
    adc \current+2,r20
    adc \current+3,r21
    sub \current,r22
    sbc \current+1,r23
    sbc \current+2,r24
    sbc \current+3,r25
    STAGE_STORE \current,\offset
    movw \current,r18
    movw \current+2,r20
.endm
.macro STAGE_PROLOGUE
.irp r,8,9,10,11,12,13,14,15,16,17,28,29
    push \r
.endr
    movw r28,r24
    movw r16,r22
.endm
.macro STAGE_Q14
    SPEEX_LSP_Q14_BODY 16
.endm
.macro STAGE_P1
    SPEEX_LSP_P1_BODY 16
.endm
.global speex_avr_lsp_stage4
.type speex_avr_lsp_stage4,@function
speex_avr_lsp_stage4:
    STAGE_PROLOGUE
    STAGE_LOAD 8,16
    STAGE_LOAD 12,12
    STAGE_PRODUCT 8
    STAGE_BOUNDARY 12,20
    STAGE_PRODUCT 12
    STAGE_LOAD 18,8
    STAGE_INNER 8,16
    rjmp .Lstage_from3
.size speex_avr_lsp_stage4,.-speex_avr_lsp_stage4
.global speex_avr_lsp_stage3
.type speex_avr_lsp_stage3,@function
speex_avr_lsp_stage3:
    STAGE_PROLOGUE
    STAGE_LOAD 12,12
    STAGE_LOAD 8,8
    STAGE_PRODUCT 12
    STAGE_BOUNDARY 8,16
.Lstage_from3:
    STAGE_PRODUCT 8
    STAGE_LOAD 18,4
    STAGE_INNER 12,12
    rjmp .Lstage_tail2
.size speex_avr_lsp_stage3,.-speex_avr_lsp_stage3
.global speex_avr_lsp_stage2
.type speex_avr_lsp_stage2,@function
speex_avr_lsp_stage2:
    STAGE_PROLOGUE
    STAGE_LOAD 8,8
    STAGE_LOAD 12,4
    STAGE_PRODUCT 8
    STAGE_BOUNDARY 12,12
.Lstage_tail2:
    STAGE_PRODUCT 12,1
    sub r8,r22
    sbc r9,r23
    sbc r10,r24
    sbc r11,r25
    ldi r18,16
    add r10,r18
    adc r11,r1
    STAGE_STORE 8,8
    clr r22
    mov r23,r16
    mov r24,r17
    .rept 2
    asr r24
    ror r23
    ror r22
    .endr
    mov r25,r24
    lsl r25
    sbc r25,r25
    sub r12,r22
    sbc r13,r23
    sbc r14,r24
    sbc r15,r25
    STAGE_STORE 12,4
.irp r,29,28,17,16,15,14,13,12,11,10,9,8
    pop \r
.endr
    clr r1
    ret
.size speex_avr_lsp_stage2,.-speex_avr_lsp_stage2
