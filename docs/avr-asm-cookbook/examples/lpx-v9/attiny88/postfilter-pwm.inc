/* Apply de-emphasis and brightness and form the PWM byte in main. */
	lds r22,_ZN17Lpx4TinyRomPlayer7decoderE+6
	lds r23,_ZN17Lpx4TinyRomPlayer7decoderE+6+1
	cp r22,__zero_reg__
	cpc r23,__zero_reg__
	breq .L160
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+16
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+16+1
	rcall _ZL26lpx4PreparedAttenuationQ14ij
/* #APP */

	add r28,r24
	adc r29,r25
	brvc 1f
	brmi 2f
	ldi r28,1
	ldi r29,128
	rjmp 3f
	2:
	ldi r28,255
	ldi r29,127
	rjmp 3f
	1: cpi r29,128
	brne 3f
	.if 1
	cpi r28,1
	adc r28,__zero_reg__
	.else
	tst r28
	brne 3f
	inc r28
	.endif
	3:

/* #NOAPP */
.L160:
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+16
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+16+1
	sts _ZN17Lpx4TinyRomPlayer7decoderE+16+1,r29
	sts _ZN17Lpx4TinyRomPlayer7decoderE+16,r28
/* #APP */

	mov r18,r29
	subi r18,192
	brpl 1f
	clr r28
	ldi r29,64
	sbrc r18,6
	ori r29,128
	1:

/* #NOAPP */
	lds r22,_ZN17Lpx4TinyRomPlayer7decoderE+8
	lds r23,_ZN17Lpx4TinyRomPlayer7decoderE+8+1
	cp r22,__zero_reg__
	cpc r23,__zero_reg__
	breq .L161
/* #APP */

	mov r18,r25
	subi r18,192
	brpl 1f
	clr r24
	ldi r25,64
	sbrc r18,6
	ori r25,128
	1:

/* #NOAPP */
	rcall _ZL26lpx4PreparedAttenuationQ14ij
	sub r28,r24
	sbc r29,r25
/* #APP */

	mov r24,r29
	subi r24,192
	brpl 1f
	clr r28
	ldi r29,64
	sbrc r24,6
	ori r29,128
	1:

/* #NOAPP */
.L161:
/* #APP */

	subi r29,192
	movw r24,r28
	clr r18
	.rept 2
	lsl r24
	rol r25
	rol r18
	.endr
	add r28,r25
	adc r29,r18
	subi r28,192
	sbci r29,0
	lsl r28
	rol r29
	brcc 1f
	lsl r29
	sbc r29,r29
	com r29
	1:

/* #NOAPP */
	mov r28,r29
