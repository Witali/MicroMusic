/* Convert spectral anchors into the LPC coefficient set. */
	.section	.text._ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10,"ax",@progbits
	.type	_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10, @function
_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10:
	ldi r26,lo8(12)
	ldi r27,0
	ldi r30,lo8(gs(1f))
	ldi r31,hi8(gs(1f))
	rjmp __prologue_saves__+((18 - 16) * 2)
1:
/* prologue: function */
/* frame size = 12 */
/* stack size = 28 */
.L__stack_usage = 28
	mov r15,r22
	mov r9,r23
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+25
	subi r18,lo8(-(3))
	andi r18,lo8(-4)
	std Y+1,r18
	subi r18,lo8(-(24))
	std Y+9,r18
	ldd r16,Y+1
	mov r30,r16
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	mov r12,__zero_reg__
	ldi r19,lo8(16)
	mov r13,r19
	mov r14,__zero_reg__
	st Z,r12
	std Z+1,r13
	std Z+2,r14
	mov r30,r18
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	st Z,r12
	std Z+1,r13
	std Z+2,r14
	cpi r24,lo8(16)
	brne .+2
	rjmp .L17
	ldi r20,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+336)
	ldi r21,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+336)
	tst r24
	brne .+2
	rjmp .L18
	ldi r24,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+346)
	ldi r25,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+346)
.L2:
	movw r10,r20
	movw r4,r24
	ldi r19,0
.L12:
	movw r26,r10
	ld r24,X+
	movw r10,r26
	movw r30,r4
	ld r25,Z+
	movw r4,r30
	add r24,r25
	subi r24,lo8(-(-1))
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+26
	sbrs r25,1
	lsl r24
.L3:
	ldi r30,lo8(_ZL10cosineEven+128)
	ldi r31,hi8(_ZL10cosineEven+128)
/* #APP */

	subi r24,64
	bst r24,7
	brtc 1f
	neg r24
	1: lsl r24
	sub r30,r24
	sbc r31,__zero_reg__
	lpm r16,Z+
	lpm r17,Z
	brtc 2f
	com r17
	neg r16
	sbci r17,255
	2:

/* #NOAPP */
	std Y+3,r17
	std Y+2,r16
	mov r20,r19
	andi r20,lo8(1)
	sbrc r19,0
	rjmp .L4
	ldd r27,Y+1
	cpi r19,lo8(2)
	brlo .+2
	rjmp .L16
	ldd r30,Y+1
	ldi r24,0
	ldi r25,lo8(16)
.L15:
	ldd r22,Y+2
	ldd r23,Y+3
	add r24,r22
	adc r25,r23
	movw r12,r24
	lsl r25
	sbc r14,r14
	ldi r18,lo8(4)
	add r18,r30
	mov r22,r18
	ldi r23,0
	subi r22,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r23,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	movw r26,r22
	st X+,r12
	st X+,r13
	st X,r14
	tst r20
	breq .L6
	com r14
	com r13
	com r12
	adc r12,__zero_reg__
	adc r13,__zero_reg__
	adc r14,__zero_reg__
.L6:
	subi r30,lo8(-(8))
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
.L33:
	st Z,r12
	std Z+1,r13
	std Z+2,r14
	subi r19,lo8(-(1))
	cpi r19,lo8(10)
	breq .+2
	rjmp .L12
	ldd r20,Y+1
	subi r20,lo8(-(4))
	ldd r18,Y+1
	subi r18,lo8(-(28))
	mov r22,r15
	mov r23,r9
	ldi r21,lo8(4)
	ldi r19,0
.L14:
	mov r26,r20
	ldi r27,0
	subi r26,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r27,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	mov r30,r18
	ldi r31,0
	movw r16,r30
	subi r16,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r17,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	ld r24,X+
	ld r25,X+
	ld r26,X
	movw r30,r16
	ld  r12,Z
	ldd r13,Z+1
	ldd r14,Z+2
	add r24,r12
	adc r25,r13
	adc r26,r14
	mov __tmp_reg__,r26
	lsl r0
	sbc r27,r27
/* #APP */

	sbrs r26,7
	rjmp 1f
	subi r24,255
	sbci r25,255
	sbci r26,255
	1: inc r26
	cpi r26,2
	brlo 3f
	ldi r24,255
	ldi r25,127
	cpi r26,129
	brlo 2f
	ldi r24,1
	ldi r25,128
	rjmp 2f
	3: cpi r26,1
	ror r25
	ror r24
	cpi r25,128
	brne 2f
	cpi r24,1
	adc r24,__zero_reg__
	2:

/* #NOAPP */
	movw r30,r22
	st Z+,r24
	st Z+,r25
	movw r22,r30
	subi r18,lo8(-(4))
	cpi r19,lo8(4)
	brne .+2
	rjmp .L20
	add r20,r21
.L13:
	subi r19,lo8(-(1))
	cpi r19,lo8(10)
	breq .+2
	rjmp .L14
/* epilogue start */
	adiw r28,12
	ldi r30, lo8(16)
	rjmp __epilogue_restores__ + ((18 - 16) * 2)
.L17:
	ldi r20,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+346)
	ldi r21,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+346)
.L18:
	movw r24,r20
	rjmp .L2
.L16:
	mov r24,r19
	andi r24,lo8(-2)
	cpse r20,__zero_reg__
	rjmp .L8
	subi r24,lo8(-(2))
	lsl r24
	add r24,r27
	ldi r30,lo8(-4)
	add r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	ld  r12,Z
	ldd r13,Z+1
	ldd r14,Z+2
	movw r6,r12
	mov r8,r14
.L9:
	subi r27,lo8(-(4))
	std Y+12,r27
.L11:
/* #APP */

	mov r20,r12
	swap r20
	andi r20,15
	mov r25,r13
	swap r25
	andi r25,240
	or r20,r25
	mov r21,r13
	swap r21
	andi r21,15
	mov r25,r14
	swap r25
	andi r25,240
	or r21,r25

/* #NOAPP */
	movw r30,r20
	subi r30,-9
	sbci r31,-62
	ldi r22,lo8(18)
	ldi r23,lo8(122)
/* #APP */

	cp r30,r22
	cpc r31,r23
	sbc r25,r25

/* #NOAPP */
	mov r30,r12
	andi r30,lo8(15)
	cpse r25,__zero_reg__
	rjmp .L10
	sbrs r21,7
	rjmp .L10
	tst r30
	breq .L10
	subi r20,-1
	sbci r21,-1
	subi r30,lo8(-(-16))
.L10:
	ldd r16,Y+2
	ldd r17,Y+3
/* #APP */

	clr r26
	clr r27
	.rept 4
	lsr r30
	brcc 1f
	add r26,r16
	adc r27,r17
	1: asr r27
	ror r26
	.endr
	sbrs r30,3
	rjmp 2f
	sub r26,r16
	sbc r27,r17
	2:

/* #NOAPP */
	std Y+11,r27
	std Y+10,r26
	mov r30,r25
	mov __tmp_reg__,r25
	lsl r0
	sbc r31,r31
	and r30,r26
	and r31,r27
	movw r22,r16
/* #APP */

	mov r17,r30
	mov r18,r31
	mov r16,r20
	lsr r16
	clt
	2:
	.rept 7
	brcc 1f
	add r17,r22
	adc r18,r23
	1: asr r18
	ror r17
	ror r16
	.endr
	brts 3f
	brcc 1f
	add r17,r22
	adc r18,r23
	1: asr r18
	ror r17
	mov r16,r21
	lsr r16
	set
	rjmp 2b
	3:
	brcc 1f
	sub r17,r22
	sbc r18,r23
	1: asr r18
	ror r17
	ror r16

/* #NOAPP */
	ldi r30,lo8(-8)
	add r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	ld  r20,Z
	ldd r21,Z+1
	ldd r22,Z+2
	std Y+6,r20
	std Y+7,r21
	std Y+8,r22
	mov r20,r24
	ldi r21,0
	movw r26,r20
	subi r26,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r27,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	com r25
	ldd r21,Y+11
	and r25,r21
	mov r20,r25
	lsl r25
	sbc r21,r21
	sbc r22,r22
	add r20,r16
	adc r21,r17
	adc r22,r18
	ldd r16,Y+6
	ldd r17,Y+7
	ldd r18,Y+8
	add r20,r16
	adc r21,r17
	adc r22,r18
	add r6,r20
	adc r7,r21
	adc r8,r22
	st X+,r6
	st X+,r7
	st X,r8
	subi r24,lo8(-(-4))
	movw r6,r12
	mov r8,r14
	ldd r17,Y+12
	cpse r24,r17
	rjmp .L19
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	ldd r20,Y+2
	ldd r21,Y+3
	add r12,r20
	adc r13,r21
	adc r14,__zero_reg__
	sbrc r21,7
	dec r14
	rjmp .L33
.L8:
	subi r24,lo8(-(65))
	lsl r24
	lsl r24
	add r24,r27
	ldi r30,lo8(-4)
	add r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	ld  r12,Z
	ldd r13,Z+1
	ldd r14,Z+2
	ldi r30,lo8(4)
	add r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	movw r6,r12
	mov r8,r14
	ldd r16,Y+2
	ldd r17,Y+3
	sub r6,r16
	sbc r7,r17
	sbc r8,__zero_reg__
	sbrc r17,7
	inc r8
	st Z,r6
	std Z+1,r7
	std Z+2,r8
	mov r6,__zero_reg__
	ldi r25,lo8(-16)
	mov r7,r25
	clr r8
	dec r8
	rjmp .L9
.L19:
	ldd r12,Y+6
	ldd r13,Y+7
	ldd r14,Y+8
	rjmp .L11
.L20:
	ldi r21,lo8(-4)
	rjmp .L13
.L4:
	ldd r27,Y+9
	cpi r19,lo8(1)
	breq .+2
	rjmp .L16
	ldd r30,Y+9
	ldi r24,0
	ldi r25,lo8(-16)
	rjmp .L15
	.size	_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10, .-_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10
