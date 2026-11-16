/* Convert spectral anchors into the LPC coefficient set. */
	.section	.text._ZL17polyDirectProductli,"ax",@progbits
	.type	_ZL17polyDirectProductli, @function
_ZL17polyDirectProductli:
	push r16
	push r17
/* prologue: function */
/* frame size = 0 */
/* stack size = 2 */
.L__stack_usage = 2
	movw r16,r22
	movw r18,r24
/* #APP */

	clr r30
	mul r16,r20
	movw r22,r0
	mulsu r21,r17
	movw r24,r0
	mul r20,r17
	add r23,r0
	adc r24,r1
	adc r25,r30
	mulsu r21,r16
	sbc r25,r30
	add r23,r0
	adc r24,r1
	adc r25,r30
	mulsu r18,r20
	add r24,r0
	adc r25,r1
	mul r18,r21
	add r25,r0
	clr __zero_reg__

/* epilogue start */
/* #NOAPP */
	pop r17
	pop r16
	ret
	.size	_ZL17polyDirectProductli, .-_ZL17polyDirectProductli
	.section	.text._ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8,"ax",@progbits
	.type	_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8, @function
_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8:
	ldi r26,lo8(6)
	ldi r27,0
	ldi r30,lo8(gs(1f))
	ldi r31,hi8(gs(1f))
	jmp __prologue_saves__+((18 - 18) * 2)
1:
/* prologue: function */
/* frame size = 6 */
/* stack size = 24 */
.L__stack_usage = 24
	std Y+3,r22
	std Y+4,r23
	lds r18,_ZL7decoder+25
	subi r18,lo8(-(3))
	andi r18,lo8(-4)
	std Y+5,r18
	ldi r17,lo8(48)
	mov r7,r17
	add r7,r18
	mov r30,r18
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	ldi r20,0
	ldi r21,lo8(16)
	ldi r22,0
	ldi r23,0
	st Z,r20
	std Z+1,r21
	std Z+2,r22
	std Z+3,r23
	mov r30,r7
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	st Z,r20
	std Z+1,r21
	std Z+2,r22
	std Z+3,r23
	ldi r25,0
	ldi r16,3
	1:
	asr r25
	ror r24
	dec r16
	brne 1b
	mov r3,r24
	ldi r25,lo8(2)
	sub r25,r24
	std Y+1,r25
	ldi r16,lo8(_ZL7decoder+336)
	ldi r17,hi8(_ZL7decoder+336)
	std Y+6,__zero_reg__
.L28:
	movw r26,r16
	ld r30,X+
	movw r16,r26
	adiw r26,9
	ld r24,X
	ldd r27,Y+1
	mul r30,r27
	mov r30,r0
	clr r1
	subi r30,lo8(-(-1))
	mul r3,r24
	add r30,r0
	clr __zero_reg__
	lds r24,_ZL7decoder+26
	lsr r24
	ldi r18,lo8(1)
	eor r24,r18
	andi r24,1
	rjmp 2f
	1:
	lsl r30
	2:
	dec r24
	brpl 1b
	mov r24,r30
	cpi r30,lo8(65)
	brlo .L15
	ldi r19,lo8(-128)
	sub r19,r30
	mov r30,r19
.L15:
	ldi r31,0
	lsl r30
	rol r31
	subi r30,lo8(-(_ZL10cosineEven))
	sbci r31,hi8(-(_ZL10cosineEven))
/* #APP */

	lpm r18, Z+
	lpm r19, Z

/* #NOAPP */
	cpi r24,lo8(65)
	brlo .L16
	neg r19
	neg r18
	sbc r19,__zero_reg__
.L16:
	clr r4
	clr r5
	sub r4,r18
	sbc r5,r19
	ldd r20,Y+6
	andi r20,lo8(1)
	ldd r21,Y+6
	sbrc r21,0
	rjmp .L17
	ldd r27,Y+6
	ldd r25,Y+5
	cpi r27,lo8(2)
	brlo .+2
	rjmp .L33
	ldd r30,Y+5
	ldi r24,0
	ldi r25,lo8(16)
.L32:
	movw r12,r24
	sub r12,r18
	sbc r13,r19
	mov __tmp_reg__,r13
	lsl r0
	sbc r14,r14
	sbc r15,r15
	ldi r26,lo8(4)
	add r26,r30
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	st X+,r12
	st X+,r13
	st X+,r14
	st X,r15
	sbiw r26,3
	tst r20
	breq .L19
	com r15
	com r14
	com r13
	com r12
	adc r12,__zero_reg__
	adc r13,__zero_reg__
	adc r14,__zero_reg__
	adc r15,__zero_reg__
.L19:
	ldi r26,lo8(8)
	add r26,r30
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	st X+,r12
	st X+,r13
	st X+,r14
	st X,r15
	sbiw r26,3
	subi r30,lo8(-(12))
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	mov __tmp_reg__,r25
	lsl r0
	sbc r26,r26
	sbc r27,r27
.L52:
	st Z,r24
	std Z+1,r25
	std Z+2,r26
	std Z+3,r27
	ldd r25,Y+6
	subi r25,lo8(-(1))
	std Y+6,r25
	cpi r25,lo8(10)
	breq .+2
	rjmp .L28
	ldd r16,Y+3
	ldd r17,Y+4
	ldd r19,Y+5
	subi r19,lo8(-(52))
	ldi r24,0
	ldi r20,lo8(11)
.L31:
	ldi r18,lo8(1)
	add r18,r24
	mov r26,r20
	sub r26,r18
	cpi r24,lo8(5)
	brsh .L29
	mov r26,r18
.L29:
	lsl r26
	lsl r26
	ldd r27,Y+5
	add r26,r27
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	mov r22,r19
	ldi r23,0
	subi r22,lo8(-(_ZL7decoder+74))
	sbci r23,hi8(-(_ZL7decoder+74))
	ld r24,X+
	ld r25,X+
	ld __tmp_reg__,X+
	ld r27,X
	mov r26,__tmp_reg__
	movw r30,r22
	ld r12,Z
	ldd r13,Z+1
	ldd r14,Z+2
	ldd r15,Z+3
	add r24,r12
	adc r25,r13
	adc r26,r14
	adc r27,r15
	mov __tmp_reg__,r27
	lsl __tmp_reg__
	adc r24,__zero_reg__
	adc r25,__zero_reg__
	adc r26,__zero_reg__
	adc r27,__zero_reg__
	asr r27
	ror r26
	ror r25
	ror r24
	cpi r24,1
	ldi r31,-128
	cpc r25,r31
	ldi r31,-1
	cpc r26,r31
	cpc r27,r31
	brge .+2
	rjmp .L37
	cp r24,__zero_reg__
	ldi r21,-128
	cpc r25,r21
	cpc r26,__zero_reg__
	cpc r27,__zero_reg__
	brlt .+2
	rjmp .L38
.L30:
	movw r26,r16
	st X+,r24
	st X+,r25
	movw r16,r26
	subi r19,lo8(-(4))
	mov r24,r18
	cpi r18,lo8(10)
	breq .+2
	rjmp .L31
/* epilogue start */
	adiw r28,6
	ldi r30, lo8(18)
	jmp __epilogue_restores__ + ((18 - 18) * 2)
.L33:
	ldd r24,Y+6
	andi r24,lo8(-2)
	ldi r30,lo8(2)
	add r30,r24
	movw r12,r4
	mov __tmp_reg__,r5
	lsl r0
	sbc r14,r14
	sbc r15,r15
	cpse r20,__zero_reg__
	rjmp .L21
	ldi r31,0
	asr r31
	ror r30
	mov r24,r30
	ldi r26,lo8(-1)
	add r26,r30
	lsl r26
	lsl r26
	add r26,r25
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	ld r8,X+
	ld r9,X+
	ld r10,X+
	ld r11,X
	lsl r30
	lsl r30
	add r30,r25
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	st Z,r8
	std Z+1,r9
	std Z+2,r10
	std Z+3,r11
.L22:
	lsl r24
	lsl r24
	mov r6,r24
	add r6,r25
	subi r25,lo8(-(4))
	std Y+2,r25
.L27:
	movw r26,r10
	movw r24,r8
	subi r24,112
	sbci r25,47
	sbci r26,-4
	sbci r27,-1
	cpi r24,33
	sbci r25,-95
	sbci r26,7
	cpc r27,__zero_reg__
	brlo .+2
	rjmp .L24
	movw r20,r4
	movw r24,r10
	movw r22,r8
	call _ZL17polyDirectProductli
/* #APP */

	mov r22,r23
	mov r23,r24
	mov r24,r25
	.rept 4
	asr r24
	ror r23
	ror r22
	.endr
	lsl r25
	sbc r25,r25

/* #NOAPP */
.L25:
	ldi r30,lo8(-8)
	add r30,r6
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	ld r8,Z
	ldd r9,Z+1
	ldd r10,Z+2
	ldd r11,Z+3
	mov r18,r6
	ldi r19,0
	movw r30,r18
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	movw r20,r22
	movw r22,r24
	add r20,r8
	adc r21,r9
	adc r22,r10
	adc r23,r11
	ld r24,Z
	ldd r25,Z+1
	ldd r26,Z+2
	ldd r27,Z+3
	add r24,r20
	adc r25,r21
	adc r26,r22
	adc r27,r23
	st Z,r24
	std Z+1,r25
	std Z+2,r26
	std Z+3,r27
	ldi r23,lo8(-4)
	add r6,r23
	ldd r24,Y+2
	cpse r6,r24
	rjmp .L27
	mov r30,r6
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	ld r24,Z
	ldd r25,Z+1
	ldd r26,Z+2
	ldd r27,Z+3
	add r24,r12
	adc r25,r13
	adc r26,r14
	adc r27,r15
	rjmp .L52
.L21:
	subi r24,lo8(-(1))
	mov r30,r24
	lsl r30
	lsl r30
	mov r26,r30
	add r26,r25
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	ld r20,X+
	ld r21,X+
	ld r22,X+
	ld r23,X
	ldi r26,lo8(8)
	add r26,r30
	add r26,r25
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	st X+,r20
	st X+,r21
	st X+,r22
	st X,r23
	sbiw r26,3
	ldi r26,lo8(-4)
	add r26,r30
	add r26,r25
	ldi r27,0
	subi r26,lo8(-(_ZL7decoder+74))
	sbci r27,hi8(-(_ZL7decoder+74))
	ld r8,X+
	ld r9,X+
	ld r10,X+
	ld r11,X
	sbrs r23,7
	rjmp .L35
	clr r20
	clr r21
	movw r22,r20
	sub r20,r12
	sbc r21,r13
	sbc r22,r14
	sbc r23,r15
.L23:
	subi r30,lo8(-(4))
	add r30,r25
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	add r20,r8
	adc r21,r9
	adc r22,r10
	adc r23,r11
	st Z,r20
	std Z+1,r21
	std Z+2,r22
	std Z+3,r23
	rjmp .L22
.L35:
	movw r22,r14
	movw r20,r12
	rjmp .L23
.L24:
	movw r26,r10
	movw r24,r8
	ldi r23,4
	1:
	asr r27
	ror r26
	ror r25
	ror r24
	dec r23
	brne 1b
	movw r18,r24
	mov r21,r8
	andi r21,lo8(15)
	sbrs r11,7
	rjmp .L26
	tst r21
	breq .L26
	subi r18,-1
	sbci r19,-1
	subi r21,lo8(-(-16))
.L26:
	movw r22,r4
/* #APP */

	clr r2
	muls r19,r23
	movw r26,r0
	mul r18,r22
	movw r24,r0
	mulsu r19,r22
	sbc r27,r2
	add r25,r0
	adc r26,r1
	adc r27,r2
	mulsu r23,r18
	sbc r27,r2
	add r25,r0
	adc r26,r1
	adc r27,r2
	clr __zero_reg__


	mulsu r21,r22
	movw r8,r0
	mov r10,r1
	lsl r10
	sbc r10,r10
	muls r21,r23
	add r9,r0
	adc r10,r1
	mov r11,r10
	lsl r11
	sbc r11,r11
	clr __zero_reg__


	mov r8,r9
	mov r9,r10
	mov r10,r11
	.rept 4
	asr r10
	ror r9
	ror r8
	.endr
	lsl r11
	sbc r11,r11

/* #NOAPP */
	mov r24,r25
	mov r25,r26
	mov r26,r27
	clr r27
	sbrc r26,7
	dec r27
	movw r22,r24
	movw r24,r26
	add r22,r8
	adc r23,r9
	adc r24,r10
	adc r25,r11
	rjmp .L25
.L37:
	ldi r24,lo8(1)
	ldi r25,lo8(-128)
	rjmp .L30
.L38:
	ldi r24,lo8(-1)
	ldi r25,lo8(127)
	rjmp .L30
.L17:
	ldd r30,Y+6
	mov r25,r7
	cpi r30,lo8(1)
	breq .+2
	rjmp .L33
	mov r30,r7
	ldi r24,0
	ldi r25,lo8(-16)
	rjmp .L32
	.size	_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8, .-_ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8
