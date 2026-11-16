/* Traverse the LPC history in main and store the new synthesized sample. */
	movw r30,r4
	movw r26,r6
/* #APP */

	bst r28,0
	.if 0
	.rept 4
	lsl r8
	rol r9
	rol r10
	rol r11
	.endr
	.endif
	ldi r17,10
	1:
	LPX_LOAD_LPC_TAP
	2:
	mov r22,r20
	tst r22
	brne 18f
	tst r21
	brne 18f
	rjmp 5f
	18:
	brtc 11f
	cpi r21,127
	brne 10f
	cpi r20,255
	breq 12f
	10: cpi r21,128
	brne 11f
	cpi r20,1
	brne 11f
	12: mov r24,r18
	mov r25,r19
	clr r23
	asr r25
	ror r24
	ror r23
	clr r20
	sbrc r19,7
	dec r20
	cp __zero_reg__,r18
	sbrc r21,7
	clc
	sbc r23,r19
	sbc r24,r20
	sbc r25,r20
	sbrs r21,7
	rjmp 8f
	com r25
	com r24
	neg r23
	sbci r24,255
	sbci r25,255
	rjmp 8f
	11:
	clr r24
	clr r25
	.rept 8
	lsr r22
	brcc 3f
	add r24,r18
	adc r25,r19
	3: ror r25
	ror r24
	.endr
	mov r22,r21
	subi r22,248
	cpi r22,16
	brsh 9f
	mov r23,r24
	mov r24,r25
	clr r25
	subi r22,8
	breq 19f
	brmi 6f
	18: add r23,r18
	adc r24,r19
	adc r25,__zero_reg__
	dec r22
	brne 18b
	19: rjmp 7f
	6: sub r23,r18
	sbc r24,r19
	sbc r25,__zero_reg__
	inc r22
	brne 6b
	rjmp 7f
	9: mov r23,r21
	lsr r23
	.rept 3
	brcc 3f
	add r24,r18
	adc r25,r19
	3: ror r25
	ror r24
	ror r23
	brcc 3f
	add r24,r18
	adc r25,r19
	3: ror r25
	ror r24
	ror r23
	.endr
	brcc 3f
	add r24,r18
	adc r25,r19
	3: ror r25
	ror r24
	ror r23
	brcc 3f
	sub r24,r18
	sbc r25,r19
	3: ror r25
	ror r24
	ror r23
	7: sbrs r19,7
	rjmp 8f
	sub r24,r20
	sbc r25,r21
	8:
	andi r23,240
	sub r8,r23
	sbc r9,r24
	sbc r10,r25
	sbc r11,__zero_reg__
	sbrc r25,7
	inc r11
	5:
	dec r17
	breq 2f
	rjmp 1b
	2:
	.if !1
	.rept 4
	asr r11
	ror r10
	ror r9
	ror r8
	.endr
	.endif

/* #NOAPP */
	movw r26,r10
	movw r24,r8
/* #APP */

	subi r26,248
	sbci r27,255
	cpi r26,16
	cpc r27,__zero_reg__
	brsh 1f
	swap r24
	swap r25
	mov r18,r25
	andi r18,240
	or r24,r18
	andi r25,15
	swap r26
	subi r26,128
	or r25,r26
	cpi r25,128
	brne 2f
	cpi r24,1
	adc r24,__zero_reg__
	rjmp 2f
	1: ldi r24,255
	ldi r25,127
	sbrs r27,7
	rjmp 2f
	ldi r24,1
	ldi r25,128
	2:

/* #NOAPP */
	movw r28,r24
	std Z+1,r25
	st Z,r24
