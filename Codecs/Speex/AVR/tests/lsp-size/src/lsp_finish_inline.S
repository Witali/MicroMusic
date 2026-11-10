/* Original project implementation: AVR5 / ATmega328P / GNU AVR ABI.
 * p r25:r24 and q r23:r22 address symmetric int32 half-polynomials;
 * p[0]==q[0]==2^20. ak r21:r20 addresses disjoint int16 output.
 * Order 8 reads p/q[1..4] once (32 bytes), writes 8 coefficients (16 bytes).
 * Order 10 reads p/q[1..5] once (40 bytes), writes 10 coefficients (20 bytes).
 * Each S+D and S-D wraps modulo 32, rounds separately, then clips to +/-32767.
 * Save r2:r3, r6..r17 and Y (16 bytes); there are no local calls or extra return bytes.
 * X/Z track inputs, Y forward output, r2:r3 reverse output. r0:r1 holds Z
 * only while storing a mirror pair; r1 is cleared at the external return.
 * No MUL, CLI, IO, static RAM or external C calls. Explicit C fallback and
 * architecture plus assembly-enable selection remain in nb3_lsp_finish.h.
 * Polynomial equations derive from Xiph lsp.c, retained with its license
 * under vendor/speex-1.2.1/libspeex; this assembly code is original. */
.macro FINISH_ROUND
    subi r18,0x80
    sbci r19,0xff
    sbci r20,0xff
    sbci r21,0xff
    tst r21
    brmi .Lfinish_negative_\@
    brne .Lfinish_positive_clip_\@
    sbrs r20,7
    rjmp .Linline_done_\@
.Lfinish_positive_clip_\@:
    ldi r19,0xff
    ldi r20,0x7f
    rjmp .Linline_done_\@
.Lfinish_negative_\@:
    cpi r21,0xff
    brne .Lfinish_negative_\@_clip_\@
    cpi r20,0x80
    brlo .Lfinish_negative_\@_clip_\@
    brne .Lfinish_round_done_\@
    tst r19
    brne .Lfinish_round_done_\@
.Lfinish_negative_\@_clip_\@:
    ldi r19,1
    ldi r20,0x80
.Lfinish_round_done_\@:
.Linline_done_\@:
.endm
.section .text.speex_lsp_finish_loop,"ax",@progbits
.global speex_avr_lsp_finish8
.type speex_avr_lsp_finish8,@function
speex_avr_lsp_finish8:
    ldi r18,16
    rjmp .Lfinish_body
.size speex_avr_lsp_finish8,.-speex_avr_lsp_finish8
.global speex_avr_lsp_finish10
.type speex_avr_lsp_finish10,@function
speex_avr_lsp_finish10:
    ldi r18,20
.size speex_avr_lsp_finish10,.-speex_avr_lsp_finish10
.type speex_lsp_finish_loop_body,@function
speex_lsp_finish_loop_body:
.Lfinish_body:
.irp reg,2,3,6,7,8,9,10,11,12,13,14,15,16,17,28,29
    push \reg
.endr
    movw r26,r24
    movw r30,r22
    movw r28,r20
    movw r2,r20
    add r2,r18
    adc r3,r1
    adiw r26,4
    adiw r30,4
    clr r6
    clr r7
    ldi r18,0x10
    mov r8,r18
    clr r9
    movw r10,r6
    movw r12,r8
.Lfinish_pair:
.irp reg,14,15,16,17
    ld \reg,X+
.endr
.irp reg,22,23,24,25
    ld \reg,Z+
.endr
    add r6,r14
    adc r7,r15
    adc r8,r16
    adc r9,r17
    sub r10,r22
    sbc r11,r23
    sbc r12,r24
    sbc r13,r25
    movw r18,r6
    movw r20,r8
    sub r18,r10
    sbc r19,r11
    sbc r20,r12
    sbc r21,r13
    FINISH_ROUND
    st Y+,r19
    st Y+,r20
    movw r18,r6
    movw r20,r8
    add r18,r10
    adc r19,r11
    adc r20,r12
    adc r21,r13
    FINISH_ROUND
    movw r0,r30
    movw r30,r2
    st -Z,r20
    st -Z,r19
    movw r2,r30
    movw r30,r0
    movw r6,r14
    movw r8,r16
    movw r10,r22
    movw r12,r24
    cp r28,r2
    cpc r29,r3
    breq .Lfinish_return
    rjmp .Lfinish_pair
.Lfinish_return:
.irp reg,29,28,17,16,15,14,13,12,11,10,9,8,7,6,3,2
    pop \reg
.endr
    clr r1
    ret
.size speex_lsp_finish_loop_body,.-speex_lsp_finish_loop_body
