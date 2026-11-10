/* Original project code, enhanced AVR5 / ATmega328P / GNU ABI.
 * p r25:r24, q r23:r22: six int32 halves with p[0]==q[0]==2^20;
 * ak r21:r20: ten int16 coefficients, disjoint from both inputs.
 * Pair symmetric outputs using S=p[j]+p[j-1], D=q[j]-q[j-1].
 * Each S+D and S-D wraps and rounds separately before +/-32767 saturation.
 * First pair uses the known equal constants; later pairs retain the newest
 * p/q words and alternate register banks, reading each p/q[1..5] once.
 * Exactly 40 input bytes read, 20 output bytes written. Own saved registers:
 * r6..r17/Y (14 stack bytes); all other callee-saved registers stay intact.
 * No MUL, CLI, IO or extra RAM; r1 is cleared at external RET. C fallback
 * and architecture plus explicit enable selector: nb3_lsp_finish.h.
 * Polynomial equations derive from licensed Xiph lsp.c, retained in vendor;
 * this assembly implementation is original to this project. */
.section .text.speex_avr_lsp_finish10,"ax",@progbits
.global speex_avr_lsp_finish10
.type speex_avr_lsp_finish10,@function

/* GNU AVR register operands accept numeric expressions in macros. */
.macro NB3_FINISH_LOAD base,ptr
    ld \base,\ptr+
    ld \base+1,\ptr+
    ld \base+2,\ptr+
    ld \base+3,\ptr+
.endm

/* r18..21 hold an unrounded sum. Its low byte is discarded only after
 * adding 128 with carry through all four bytes, including signed wrap. */
.macro NB3_FINISH_OUTPUT sum,diff,offset,minus,first_constant=0
    movw r18,\sum
    movw r20,\sum+2
.if \minus
    sub r18,\diff
    sbc r19,\diff+1
    sbc r20,\diff+2
    sbc r21,\diff+3
.else
    add r18,\diff
    adc r19,\diff+1
    adc r20,\diff+2
    adc r21,\diff+3
.endif
.if \first_constant
    subi r20,0xe0
    sbci r21,0xff
.endif
    subi r18,0x80
    sbci r19,0xff
    sbci r20,0xff
    sbci r21,0xff
    tst r21
    brmi .Lfinish_negative_\@
    brne .Lfinish_positive_clip_\@
    sbrs r20,7
    rjmp .Lfinish_round_done_\@
.Lfinish_positive_clip_\@:
    ldi r19,0xff
    ldi r20,0x7f
    rjmp .Lfinish_round_done_\@
.Lfinish_negative_\@:
    cpi r21,0xff
    brne .Lfinish_negative_clip_\@
    cpi r20,0x80
    brlo .Lfinish_negative_clip_\@
    brne .Lfinish_round_done_\@
    tst r19
    brne .Lfinish_round_done_\@
.Lfinish_negative_clip_\@:
    ldi r19,1
    ldi r20,0x80
.Lfinish_round_done_\@:
    std Y+\offset,r19
    std Y+\offset+1,r20
.endm

/* Keep newP/newQ unchanged for the following pair. oldQ becomes -D,
 * so the forward output subtracts it and the mirrored output adds it. */
.macro NB3_FINISH_PAIR oldP,oldQ,newP,newQ,offset
    NB3_FINISH_LOAD \newP,X
    NB3_FINISH_LOAD \newQ,Z
    add \oldP,\newP
    adc \oldP+1,\newP+1
    adc \oldP+2,\newP+2
    adc \oldP+3,\newP+3
    sub \oldQ,\newQ
    sbc \oldQ+1,\newQ+1
    sbc \oldQ+2,\newQ+2
    sbc \oldQ+3,\newQ+3
    NB3_FINISH_OUTPUT \oldP,\oldQ,0,1
    NB3_FINISH_OUTPUT \oldP,\oldQ,\offset,0
.endm

speex_avr_lsp_finish10:
.irp reg,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push \reg
.endr
    movw r26,r24
    movw r30,r22
    movw r28,r20
    adiw r26,4
    adiw r30,4
    NB3_FINISH_LOAD 6,X
    NB3_FINISH_LOAD 10,Z
    NB3_FINISH_OUTPUT 6,10,0,0
    NB3_FINISH_OUTPUT 6,10,18,1,1
    adiw r28,2
    NB3_FINISH_PAIR 6,10,14,22,14
    adiw r28,2
    NB3_FINISH_PAIR 14,22,6,10,10
    adiw r28,2
    NB3_FINISH_PAIR 6,10,14,22,6
    adiw r28,2
    NB3_FINISH_PAIR 14,22,6,10,2
.irp reg,29,28,17,16,15,14,13,12,11,10,9,8,7,6
    pop \reg
.endr
    clr r1
    ret
.size speex_avr_lsp_finish10,.-speex_avr_lsp_finish10
