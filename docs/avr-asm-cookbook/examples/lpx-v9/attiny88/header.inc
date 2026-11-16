/* Read and validate the LPX v9 stream header in main. */
	ldi r30,lo8(_ZL5voice)
	ldi r31,hi8(_ZL5voice)
/* #APP */

	lpm r24, Z+
	lpm r25, Z

/* #NOAPP */
	cpi r24,76
	sbci r25,57
	breq .L128
.L132:
	ldi r24,lo8(1)
.L217:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+28,r24
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+28
	sts lpx25_error,r24
	ldi r24,lo8(1)
	sts lpx25_stopped,r24
.L134:
	rjmp .L134
.L128:
	ldi r30,lo8(_ZL5voice+2)
	ldi r31,hi8(_ZL5voice+2)
/* #APP */

	lpm r30, Z

/* #NOAPP */
	cpi r30,lo8(15)
	breq .L130
	mov r24,r30
	andi r24,lo8(125)
	cpi r24,lo8(4)
	breq .L130
	ldi r24,lo8(2)
	rjmp .L217
.L130:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+26,r30
	ldi r26,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+2)
	ldi r27,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+2)
	ldi r30,lo8(_ZL5voice+3)
	ldi r31,hi8(_ZL5voice+3)
	ldi r24,lo8(10)
/* #APP */

	1: lpm r25,Z+
	st X+,r25
	dec r24
	brne 1b

/* #NOAPP */
	sts _ZN17Lpx4TinyRomPlayer7decoderE+1,r31
	sts _ZN17Lpx4TinyRomPlayer7decoderE,r30
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+4
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+4+1
	sts _ZN17Lpx4TinyRomPlayer7decoderE+12+1,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+12,r24
	ldi r18,lo8(20)
	cpi r24,20
	cpc r25,__zero_reg__
	brsh .L131
	mov r18,r24
.L131:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+20,r18
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+10
	lds r19,_ZN17Lpx4TinyRomPlayer7decoderE+10+1
	sbiw r24,1
	cp r24,__zero_reg__
	sbci r25,-6
	brlo .+2
	rjmp .L132
	cpi r18,lo8(lpx_audio_end-_ZL5voice-13)
	sbci r19,hi8(lpx_audio_end-_ZL5voice-13)
	breq .+2
	rjmp .L132
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+2
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+2+1
	cpi r24,64
	sbci r25,31
	breq .+2
	rjmp .L132
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+6
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+6+1
	cpi r24,1
	ldi r19,64
	cpc r25,r19
	brlo .+2
	rjmp .L132
	lds r14,_ZN17Lpx4TinyRomPlayer7decoderE+8
	lds r15,_ZN17Lpx4TinyRomPlayer7decoderE+8+1
	ldi r20,-50
	cp r14,r20
	ldi r20,44
	cpc r15,r20
	brlo .+2
	rjmp .L132
	rcall _ZL25lpx4PrepareAttenuationQ14j
	sts _ZN17Lpx4TinyRomPlayer7decoderE+6+1,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+6,r24
	movw r24,r14
	rcall _ZL25lpx4PrepareAttenuationQ14j
	sts _ZN17Lpx4TinyRomPlayer7decoderE+8+1,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+8,r24
