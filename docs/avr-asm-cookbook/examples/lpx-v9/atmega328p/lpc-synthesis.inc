/* Traverse the LPC history in main and store the new synthesized sample. */
	movw r30,r8
	movw r26,r14
/* #APP */

	clr r16
	.if 0
	.rept 4
	lsl r4
	rol r5
	rol r6
	rol r7
	.endr
	.endif
	ld r19,-X
	ld r18,-X
	ld r21,-Z
	ld r20,-Z
	.if 1
	std Z+2,r20
	std Z+3,r21
	.endif
	muls r19,r21
	movw r24,r0
	mul r18,r20
	movw r22,r0
	mulsu r19,r20
	sbc r25,r16
	add r23,r0
	adc r24,r1
	adc r25,r16
	mulsu r21,r18
	sbc r25,r16
	add r23,r0
	adc r24,r1
	adc r25,r16
	andi r23,0xf0
	sub r4,r23
	sbc r5,r24
	sbc r6,r25
	sbc r7,r16
	sbrc r25,7
	inc r7
	.rept 9
	ld r19,-X
	ld r18,-X
	ld r21,-Z
	ld r20,-Z
	std Z+2,r20
	std Z+3,r21
	muls r19,r21
	movw r24,r0
	mul r18,r20
	movw r22,r0
	mulsu r19,r20
	sbc r25,r16
	add r23,r0
	adc r24,r1
	adc r25,r16
	mulsu r21,r18
	sbc r25,r16
	add r23,r0
	adc r24,r1
	adc r25,r16
	andi r23,0xf0
	sub r4,r23
	sbc r5,r24
	sbc r6,r25
	sbc r7,r16
	sbrc r25,7
	inc r7
	.endr
	.if !0
	.rept 4
	asr r7
	ror r6
	ror r5
	ror r4
	.endr
	.endif
	clr __zero_reg__


	lsl r5
	sbc r16,r16
	.if 0
	eor r16,r6
	brne 1f
	.else
	cp r6,r16
	brne 1f
	lsl r16
	.endif
	ror r5
	movw r16,r4
	cpi r17,128
	brne 2f
	.if 0
	cpi r16,1
	adc r16,__zero_reg__
	.else
	tst r16
	brne 2f
	inc r16
	.endif
	rjmp 2f
	1:
	ldi r16,255
	ldi r17,127
	sbrs r6,7
	rjmp 2f
	ldi r16,1
	ldi r17,128
	2:

/* #NOAPP */
	sts _ZL7decoder+52+1,r17
	sts _ZL7decoder+52,r16
