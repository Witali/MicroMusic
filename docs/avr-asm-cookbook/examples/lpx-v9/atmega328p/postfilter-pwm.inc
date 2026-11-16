/* Apply de-emphasis and brightness and form the PWM byte in main. */
	lds r24,_ZL7decoder+10
	lds r25,_ZL7decoder+10+1
	lds r26,_ZL7decoder+16
	std Y+3,r26
	lds r27,_ZL7decoder+17
	std Y+1,r27
	sbiw r24,0
	breq .L152
	movw r22,r26
	call _ZL16lpx4AttenuateQ14ji
/* #APP */

	add r16,r24
	adc r17,r25
	brvc 1f
	brmi 2f
	ldi r16,1
	ldi r17,128
	rjmp 3f
	2:
	ldi r16,255
	ldi r17,127
	rjmp 3f
	1: cpi r17,128
	brne 3f
	.if 0
	cpi r16,1
	adc r16,__zero_reg__
	.else
	tst r16
	brne 3f
	inc r16
	.endif
	3:

/* #NOAPP */
.L152:
	sts _ZL7decoder+16+1,r17
	sts _ZL7decoder+16,r16
	cpi r16,1
	ldi r30,64
	cpc r17,r30
	brlt .L153
	ldi r16,0
	ldi r17,lo8(64)
.L153:
	cp r16,__zero_reg__
	ldi r31,-64
	cpc r17,r31
	brge .L154
	ldi r16,0
	ldi r17,lo8(-64)
.L154:
	lds r24,_ZL7decoder+12
	lds r25,_ZL7decoder+12+1
	sbiw r24,0
	breq .L155
	ldd r22,Y+3
	ldd r23,Y+1
	cpi r22,1
	ldi r18,64
	cpc r23,r18
	brlt .L156
	ldi r22,0
	ldi r23,lo8(64)
.L156:
	cp r22,__zero_reg__
	ldi r19,-64
	cpc r23,r19
	brge .L157
	ldi r22,0
	ldi r23,lo8(-64)
.L157:
	call _ZL16lpx4AttenuateQ14ji
	sub r16,r24
	sbc r17,r25
	cpi r16,1
	ldi r20,64
	cpc r17,r20
	brlt .L158
	ldi r16,0
	ldi r17,lo8(64)
.L158:
	cp r16,__zero_reg__
	ldi r24,-64
	cpc r17,r24
	brge .L155
	ldi r16,0
	ldi r17,lo8(-64)
.L155:
	ldi r18,lo8(-126)
/* #APP */

	clr r24
	mulsu r17,r18
	movw r20,r0
	mul r16,r18
	add r20,r1
	adc r21,r24
	subi r20,224
	sbci r21,223
	cpi r21,64
	brlo 1f
	ldi r24,255
	sbrc r17,7
	clr r24
	rjmp 2f
	1:
	.rept 2
	lsl r20
	rol r21
	.endr
	mov r24,r21
	2:
	clr __zero_reg__

/* #NOAPP */
	std Y+3,r24
