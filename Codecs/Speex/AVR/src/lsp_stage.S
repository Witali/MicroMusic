/* Original project kernels: constant stages 2/3/4, enhanced AVR5/GNU ABI.
 * p r25:r24, f r23:r22. p0=2^20, p1 divisible by 64; each product input
 * is signed30. Polynomial/root bounds and the selectable C implementation
 * are in nb3_lsp_stage.h. Read p[stage..1] once, write p[stage+1..1].
 * The stages share their descending tail. Twelve saved bytes (r8..17/Y),
 * no extra RAM, hardware IO or interrupt masking; preserve ABI and clear r1.
 * Private general products retain the MUL result in r1 until the final P1
 * product clears it before the p0 addition. No intervening instruction
 * treats r1 as zero or calls C; the remaining tail preserves that zero.
 * Default value kernels stay byte-identical. Independent rounding and wrap
 * occur at each original product/update. IRQs must preserve interrupted r1. */
#include "lsp_stage_macros.S"
.section .text.speex_avr_lsp_stages,"ax",@progbits
.macro STAGE_PROLOGUE
.irp r,8,9,10,11,12,13,14,15,16,17,28,29
    push \r
.endr
    movw r28,r24
    movw r16,r22
.endm
.global speex_avr_lsp_stage4
.type speex_avr_lsp_stage4,@function
speex_avr_lsp_stage4:
    STAGE_PROLOGUE
    STAGE_START4
    rjmp .Lstage_from3
.size speex_avr_lsp_stage4,.-speex_avr_lsp_stage4
.global speex_avr_lsp_stage3
.type speex_avr_lsp_stage3,@function
speex_avr_lsp_stage3:
    STAGE_PROLOGUE
    STAGE_START3
.Lstage_from3:
    STAGE_FROM3
    rjmp .Lstage_tail2
.size speex_avr_lsp_stage3,.-speex_avr_lsp_stage3
.global speex_avr_lsp_stage2
.type speex_avr_lsp_stage2,@function
speex_avr_lsp_stage2:
    STAGE_PROLOGUE
    STAGE_START2
.Lstage_tail2:
    STAGE_TAIL2
.irp r,29,28,17,16,15,14,13,12,11,10,9,8
    pop \r
.endr
    ret
.size speex_avr_lsp_stage2,.-speex_avr_lsp_stage2
