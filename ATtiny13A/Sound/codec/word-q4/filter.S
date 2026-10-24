/* Eight-stage signed-word Q4 lattice plus the original 1/2 deemphasis.
 * Input excitation r15:r14 scaled to WORD_STATE_BITS fractional bits (4/6).
 * Y points at 8 little-endian word states, followed by previous output.
 * Z points at the last of 8 signed Q4 coefficients. Default is Flash;
 * WORD_COEFFICIENTS_IN_RAM selects a predecoded SRAM buffer. r27 = zero.
 * Result r24 is unsigned midpoint PWM; states and previous output updated.
 * Clobbers r14:r26, Y/Z, arithmetic flags; preserves SREG.T/I and r27.
 * No overflow guards at runtime: the encoder must qualify its exact stream.
 * This isolated kernel does not include excitation, stream parsing or IRQ.
 */
.global filter_word_q4, word_filter_end
.ifndef WORD_STATE_BITS
.equ WORD_STATE_BITS,4
.endif
.if (WORD_STATE_BITS != 4) && (WORD_STATE_BITS != 6)
.error "WORD_STATE_BITS must be 4 or 6"
.endif
filter_word_q4:
 adiw r28,14
 ld r16,Y
 ldd r17,Y+1
.ifdef WORD_COEFFICIENTS_IN_RAM
 ld r20,Z
.else
 lpm r20,Z
.endif
 movw r18,r16
 rcall mul_word_q4
 sub r14,r24
 sbc r15,r25
 ldi r26,7
word_filter_stage:
 sbiw r28,2
 sbiw r30,1
 ld r16,Y
 ldd r17,Y+1
.ifdef WORD_COEFFICIENTS_IN_RAM
 ld r20,Z
.else
 lpm r20,Z
.endif
 movw r18,r16
 rcall mul_word_q4
 sub r14,r24
 sbc r15,r25
 movw r18,r14
 rcall mul_word_q4
 add r24,r16
 adc r25,r17
 std Y+2,r24
 std Y+3,r25
 dec r26
 brne word_filter_stage
 st Y,r14
 std Y+1,r15
 ldd r16,Y+16
 ldd r17,Y+17
 movw r24,r16
 asr r25
 ror r24
 sub r16,r24
 sbc r17,r25
 add r14,r16
 adc r15,r17
 std Y+16,r14
 std Y+17,r15
.rept WORD_STATE_BITS
 asr r15
 ror r14
.endr
 ldi r24,128
 add r24,r14
 ret
word_filter_end:
