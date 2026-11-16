/* Apply bounded Q14 attenuation for the two output filters. */
	.section	.text._ZL26lpx4PreparedAttenuationQ14ij,"ax",@progbits
	.type	_ZL26lpx4PreparedAttenuationQ14ij, @function
_ZL26lpx4PreparedAttenuationQ14ij:
/* prologue: naked */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
/* #APP */

	cpi r23,64
	brsh 7f
	movw r18,r24
	movw r20,r22
	subi r19,128
	clr r24
	clr r25
	lsr r22
	brcc 4f
	movw r24,r18
	lsr r25
	ror r24
	4:
	lsr r22
	brcc 2f
	add r24,r18
	adc r25,r19
	2: ror r25
	ror r24
	clt
	5:
	.rept 6
	lsr r22
	brcc 2f
	add r24,r18
	adc r25,r19
	2: ror r25
	ror r24
	.endr
	brts 6f
	set
	mov r22,r23
	rjmp 5b
	6: lsl r20
	rol r21
	sub r24,r20
	sbc r25,r21
	ret
	7: brne 8f
	ret
	8: brpl 10f
	asr r25
	ror r24
	ret
	10: mov r24,r25
	lsl r25
	sbc r25,r25
	ret

/* epilogue start */
/* #NOAPP */
	.size	_ZL26lpx4PreparedAttenuationQ14ij, .-_ZL26lpx4PreparedAttenuationQ14ij
	.section	.text._ZL25lpx4PrepareAttenuationQ14j,"ax",@progbits
	.type	_ZL25lpx4PrepareAttenuationQ14j, @function
_ZL25lpx4PrepareAttenuationQ14j:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	cp r24,__zero_reg__
	ldi r18,32
	cpc r25,r18
	breq .L122
	cpi r24,64
	cpc r25,__zero_reg__
	brne .L123
.L122:
	subi r25,96
.L123:
/* epilogue start */
	ret
	.size	_ZL25lpx4PrepareAttenuationQ14j, .-_ZL25lpx4PrepareAttenuationQ14j
