/* Signed word * signed bounded coefficient, symmetric nearest / 2^N.
 * Q4: |coefficient| <= 15; Q5: <= 31. Input r19:r18, coefficient r20.
 * Result r25:r24. Clobbers r18:r19, r21:r23 and arithmetic flags.
 * Preserves r16:r17, r20, pointers, SREG.T/I. r27 must remain zero.
 * Negative coefficient first negates the word with 16-bit wrap, matching
 * the PC model even at -32768. A second negation forms unsigned magnitude.
 * After each stage accumulator < magnitude <= 32768, so adding magnitude
 * never overflows 16 unsigned bits. Four/five staged shifts equal one final
 * division, with the last discarded bit available for rounding.
 */
.global mul_word_q4, mul_word_q5, word_mul_round, word_mul_end
mul_word_q4:
 ldi r23,4
 rjmp word_mul_common
mul_word_q5:
 ldi r23,5
word_mul_common:
 clr r24
 clr r25
 mov r21,r20
 tst r21
 breq word_mul_return
 brpl word_mul_positive_coefficient
 neg r21
 com r19
 neg r18
 sbci r19,0xff
word_mul_positive_coefficient:
 clr r22
 tst r19
 brpl word_mul_magnitude
 inc r22
 com r19
 neg r18
 sbci r19,0xff
word_mul_magnitude:
.ifdef WORD_MUL_UNROLLED
 sbrs r23,0
 rjmp word_mul_four
 lsr r21
 brcc 1f
 add r24,r18
 adc r25,r19
1:
 lsr r25
 ror r24
word_mul_four:
.rept 4
 lsr r21
 brcc 1f
 add r24,r18
 adc r25,r19
1:
 lsr r25
 ror r24
.endr
.else
 lsr r21
 brcc word_mul_no_add
 add r24,r18
 adc r25,r19
word_mul_no_add:
 lsr r25
 ror r24
 dec r23
 brne word_mul_magnitude
.endif
word_mul_round:
 adc r24,r27
 adc r25,r27
 sbrs r22,0
 ret
 com r25
 neg r24
 sbci r25,0xff
word_mul_return:
 ret
word_mul_end:
