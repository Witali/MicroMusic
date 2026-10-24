/* Exact signed-word Q4/Q5 multiplication with early zero-bit factoring.
 * ABI and symmetric rounding match multiply.S, including -32768 wrapping.
 * Initial zero coefficient bits leave a zero accumulator: skip their shifts.
 * Once the first one is found, powers of two need only word shifts.
 */
.global mul_word_q4, mul_word_q5, word_mul_round, word_mul_end
mul_word_q4:
 ldi r23,4
 rjmp word_mul_common
mul_word_q5:
 ldi r23,5
word_mul_common:
 mov r21,r20
 tst r21
 breq word_mul_zero
 brpl word_mul_positive_coefficient
 neg r21
 com r19
 neg r18
 sbci r19,0xff
word_mul_positive_coefficient:
 clr r22
 tst r19
 brpl word_mul_seek
 inc r22
 com r19
 neg r18
 sbci r19,0xff
word_mul_seek:
 lsr r21
 brcs word_mul_first
 dec r23
 rjmp word_mul_seek
word_mul_first:
 movw r24,r18
 lsr r25
 ror r24
 dec r23
 breq word_mul_round
 tst r21
 breq word_mul_shift_only
word_mul_magnitude:
 lsr r21
 brcc word_mul_no_add
 add r24,r18
 adc r25,r19
word_mul_no_add:
 lsr r25
 ror r24
 dec r23
.ifdef WORD_MUL_ADAPTIVE
 breq word_mul_round
 tst r21
 brne word_mul_magnitude
word_mul_shift_only:
 lsr r25
 ror r24
 dec r23
 brne word_mul_shift_only
.else
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
 ret
.ifndef WORD_MUL_ADAPTIVE
word_mul_shift_only:
 lsr r25
 ror r24
 dec r23
 brne word_mul_shift_only
 rjmp word_mul_round
.endif
word_mul_zero:
 clr r24
 clr r25
 ret
word_mul_end:
