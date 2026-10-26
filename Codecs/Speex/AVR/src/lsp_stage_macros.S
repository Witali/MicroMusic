/* Shared source for single and paired stages; same arithmetic/rounding.
 * Enhanced AVR5, private r8..17/Y windows; C equations: nb3_lsp_stage.h. */
#ifndef MICROMUSIC_LSP_STAGE_MACROS
#define MICROMUSIC_LSP_STAGE_MACROS
#include "q14_macros.S"
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
.macro STAGE_Q14
    SPEEX_LSP_Q14_BODY 16,0
.endm
.macro STAGE_P1
    SPEEX_LSP_P1_BODY 16
.endm
.macro STAGE_START4
    STAGE_LOAD 8,16
    STAGE_LOAD 12,12
    STAGE_PRODUCT 8
    STAGE_BOUNDARY 12,20
    STAGE_PRODUCT 12
    STAGE_LOAD 18,8
    STAGE_INNER 8,16
.endm
.macro STAGE_START3
    STAGE_LOAD 12,12
    STAGE_LOAD 8,8
    STAGE_PRODUCT 12
    STAGE_BOUNDARY 8,16
.endm
.macro STAGE_FROM3
    STAGE_PRODUCT 8
    STAGE_LOAD 18,4
    STAGE_INNER 12,12
.endm
.macro STAGE_START2
    STAGE_LOAD 8,8
    STAGE_LOAD 12,4
    STAGE_PRODUCT 8
    STAGE_BOUNDARY 12,12
.endm
.macro STAGE_TAIL2
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
.endm
#endif
