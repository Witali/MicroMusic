/* Original project two-root constructor; enhanced AVR5 / GNU ABI.
 * p r25:r24, a r23:r22, b r21:r20. Full signed16 roots; p1=-(a+b)*64,
 * p2=2^21+ceil(a*b/256). No input-memory reads, exactly eight bytes written,
 * no own stack, IO or CLI. Caller-clobbered r0/r1,r18..27/Z only; clear r1.
 * The high-byte ADC's S=N xor V identifies the untruncated signed17 sum.
 * LDI preserves S. Both BRGE paths take two cycles and construct the
 * complement of the sign-extension byte. Negation permits +65536, then
 * byte alignment and two arithmetic shifts form the exact signed32 p1.
 * MUL scheduling follows the project's AVR201-derived avr_multiply.h,
 * with a caller-clobbered zero instead of r2. Bias includes the original
 * ceil and 2^21 constant before discarding a byte; no early rounding.
 * C fallback/architecture plus explicit-enable selection: nb3_lsp_first.h.
 * SREG/ADC semantics: Microchip AVR Instruction Set Manual, ADC SREG and
 * BRGE summary; links and proof workload are retained in the cookbook. */
.section .text.speex_avr_lsp_first,"ax",@progbits
.global speex_avr_lsp_first
.type speex_avr_lsp_first,@function
speex_avr_lsp_first:
    movw r30,r24
    movw r24,r22
    add r24,r20
    adc r25,r21
    ldi r26,0xff
    brge .Lfirst_sum_nonnegative
    clr r26
.Lfirst_sum_nonnegative:
    com r25
    neg r24
    sbci r25,0xff
    sbci r26,0xff
    clr r19
    .rept 2
    asr r26
    ror r25
    ror r24
    ror r19
    .endr
    std Z+4,r19
    std Z+5,r24
    std Z+6,r25
    std Z+7,r26
    clr r18
    muls r23,r21
    movw r26,r0
    mul r22,r20
    movw r24,r0
    mulsu r23,r20
    sbc r27,r18
    add r25,r0
    adc r26,r1
    adc r27,r18
    mulsu r21,r22
    sbc r27,r18
    add r25,r0
    adc r26,r1
    adc r27,r18
    subi r24,0x01
    sbci r25,0xff
    sbci r26,0xff
    sbci r27,0xdf
    std Z+8,r25
    std Z+9,r26
    std Z+10,r27
    lsl r27
    sbc r24,r24
    std Z+11,r24
    clr r1
    ret
.size speex_avr_lsp_first,.-speex_avr_lsp_first
