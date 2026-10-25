#include "q14_macros.S"
/* Exact generic Xiph MULT16_32_Q14 in one AVR-GCC ABI subroutine.
 * int32_t speex_avr_mul16_32_q14(int16_t a, int32_t b);
 * a r25:r24, b r23:r20, result r25:r22. No callee-saved registers, restore r1.
 * Upstream casts b>>14 to signed16: its effective operand is signed30(b).
 * Form the signed 48-bit product in r27:r22, align left by 2 and discard
 * 16 low bits. This retains upstream's floor, including negative operands
 * and all four possible values of the ignored top two input bits.
 * Original register/carry schedule; no interrupt masking or RAM scratch. */
.section .text.speex_avr_mul16_32_q14,"ax",@progbits
.global speex_avr_mul16_32_q14
.type speex_avr_mul16_32_q14, @function
speex_avr_mul16_32_q14:
    /* Generic entry normalizes signed30 before tail-calling the same core. */
    lsl r23
    lsl r23
    asr r23
    asr r23
    rjmp speex_avr_lsp_mul_q14
.size speex_avr_mul16_32_q14, .-speex_avr_mul16_32_q14

/* Fast entry requires -2^29 <= b < 2^29. Order-10 polynomial inputs have
 * |b| <= 73400331 by the absolute-value recurrence bound in compact_lsp. */
.section .text.speex_avr_lsp_mul_q14,"ax",@progbits
.global speex_avr_lsp_mul_q14
.type speex_avr_lsp_mul_q14, @function
speex_avr_lsp_mul_q14:
    movw r18, r24       /* a */
    SPEEX_LSP_Q14_BODY 18
    ret
.size speex_avr_lsp_mul_q14, .-speex_avr_lsp_mul_q14

/* Exact Q14 for the p1 polynomial coefficient, always divisible by 64.
 * int32_t speex_avr_p1_mul_q14(int16_t a,int32_t b), standard AVR GCC ABI.
 * Requires -2^29 <= b < 2^29 and b%64==0 (p1 has the tighter |b|<=8388608).
 * (a*b)>>14 == (a*(b>>6))>>8: use six MULs and a signed40 product.
 * b<<2 fits signed32; its upper three bytes are the exact signed24 b>>6.
 * Caller-clobbered registers only; no SRAM or interrupt masking, restore r1.
 * The selectable C fallback uses the exact generic Q14 helper. */
.section .text.speex_avr_p1_mul_q14,"ax",@progbits
.global speex_avr_p1_mul_q14
.type speex_avr_p1_mul_q14,@function
speex_avr_p1_mul_q14:
    movw r18,r24
    SPEEX_LSP_P1_BODY 18
    ret
.size speex_avr_p1_mul_q14,.-speex_avr_p1_mul_q14
