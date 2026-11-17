// Private AVR25 converter instruction sequence, supplied to __asm__.
// Derived from this project's d75d66e3 converter using AVR-GCC 7.3.0,
// then parameterized for dynamic objects and a declared register contract.
// The original C++ implementation remains the explicitly selectable fallback.
//
// X supplies this, r24 supplies the anchor, and r23:r22 supplies output.
// Preserved registers are r3,r4,r6,r7,r8,r14,r28,r29.
// r1,r2,r5,r10,r11,r15 are untouched. The wrapper declares all other writes.
// Object offsets are assembled from offsetof constraints in the wrapper.
// Two otherwise dead polynomial padding bytes hold the output pointer.
R"LPX4_ASM(
	.pushsection .text.lpx4_tiny_convert,"ax",@progbits
	.global lpx4_tiny_convert
	.type lpx4_tiny_convert,@function
lpx4_tiny_convert:
	push r3
	push r4
	push r6
	push r7
	push r8
	push r14
	push r28
	push r29

	; Read dynamic object fields and align the existing pitch-page workspace.
	movw r30,r26
	ldd r0,Z+lpx4_conv_profile_offset
	ldd r18,Z+lpx4_conv_ring_offset
	subi r18,lo8(-(3))
	andi r18,lo8(-4)

	mov r30,r18
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	; Initialize P0/Q0; their unused fourth bytes retain the output pointer.
	std Z+3,r22
	mov r12,__zero_reg__
	ldi r22,lo8(16)
	mov r13,r22
	mov r14,__zero_reg__
	st Z,r12
	std Z+1,r13
	std Z+2,r14

	mov r30,r18
	subi r30,lo8(-24)
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	st Z,r12
	std Z+1,r13
	std Z+2,r14
	std Z+3,r23
	movw r28,r26
	subi r28,lo8(-lpx4_conv_cur_offset)
	sbci r29,hi8(-lpx4_conv_cur_offset)
	subi r26,lo8(-lpx4_conv_old_offset)
	sbci r27,hi8(-lpx4_conv_old_offset)

	sbrc r24,4
	movw r26,r28
	tst r24
	brne 1f
	movw r28,r26
	1:

	ldi r24,0
.Llpx4_convert_9:
	; Interpolate a frequency and fetch its exact reflected cosine node.
	ld r25,X+
	ld r19,Y+
	add r25,r19
	subi r25,lo8(-(-1))
	mov r19,r0
	sbrs r19,1
	lsl r25
.Llpx4_convert_2:
	ldi r30,lo8(lpx4_tiny_cosine_even+128)
	ldi r31,hi8(lpx4_tiny_cosine_even+128)

	subi r25,64
	bst r25,7
	brtc 1f
	neg r25
	1: lsl r25
	sub r30,r25
	sbc r31,__zero_reg__
	lpm r16,Z+
	lpm r17,Z
	brtc 2f
	com r17
	neg r16
	sbci r17,255
	2:

	mov r20,r24
	andi r20,lo8(1)
	mov r19,r18
	sbrc r24,0
	subi r19,lo8(-24)
.Llpx4_convert_3:
	mov r25,r24
	andi r25,lo8(-2)
	cpse r20,__zero_reg__
	rjmp .Llpx4_convert_4
	subi r25,lo8(-(2))
	lsl r25
	add r25,r19
	ldi r20,lo8(-4)
	add r20,r25

	mov r30,r20
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	ld  r12,Z
	ldd r13,Z+1
	ldd r14,Z+2
	movw r6,r12
	mov r8,r14
.Llpx4_convert_5:
	; Descend through the three-byte polynomial coefficients.
	subi r19,lo8(-(4))
.Llpx4_convert_8:
	cp r19,r25
	brne .+2
	rjmp .Llpx4_convert_6

	mov r20,r12
	swap r20
	andi r20,15
	mov r21,r13
	swap r21
	eor r20,r21
	andi r21,15
	eor r20,r21
	mov r30,r14
	swap r30
	andi r30,240
	or r21,r30

	movw r30,r20
	subi r30,-9
	sbci r31,-62

	subi r30,lo8(31250)
	sbci r31,hi8(31250)
	sbc r9,r9

	mov r30,r12
	andi r30,lo8(15)
	cpse r9,__zero_reg__
	rjmp .Llpx4_convert_7
	sbrs r21,7
	rjmp .Llpx4_convert_7
	tst r30
	breq .Llpx4_convert_7
	subi r20,-1
	sbci r21,-1
	subi r30,lo8(-(-16))
.Llpx4_convert_7:

	; Software product with the original signed split and rounding order.
	mov r23,r30
	clr r3
	clr r4
	lsr r23
	clr r31
	rjmp 4f
	2:
	.rept 3
	brcc 1f
	add r3,r16
	adc r4,r17
	1: asr r4
	ror r3
	ror r23
	.endr
	4:
	.rept 4
	brcc 1f
	add r3,r16
	adc r4,r17
	1: asr r4
	ror r3
	ror r23
	.endr
	dec r31
	brmi 6f
	breq 8f
	brcc 1f
	add r3,r16
	adc r4,r17
	1: asr r4
	ror r3
	mov r23,r21
	lsr r23
	rjmp 2b
	6: sbrs r30,7
	rjmp 7f
	sub r3,r16
	sbc r4,r17
	7: sbrs r9,7
	clr r3
	ldi r31,2
	mov r23,r20
	lsr r23
	rjmp 2b
	8: brcc 1f
	sub r3,r16
	sbc r4,r17
	1: asr r4
	ror r3
	ror r23

	ldi r20,lo8(-8)
	add r20,r25

	mov r30,r20
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	ld  r20,Z
	ldd r21,Z+1
	ldd r22,Z+2

	mov r30,r25
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	; Accumulate and store the three-byte recurrence result.
	add r23,r20
	adc r3,r21
	adc r4,r22
	add r6,r23
	adc r7,r3
	adc r8,r4
	st Z,r6
	std Z+1,r7
	std Z+2,r8
	subi r25,lo8(-(-4))
	movw r6,r12
	mov r8,r14
	movw r12,r20
	mov r14,r22
	rjmp .Llpx4_convert_8
.Llpx4_convert_4:
	; Seed the next coefficient before descending through this factor.
	subi r25,lo8(-(65))
	lsl r25
	lsl r25
	add r25,r19
	ldi r20,lo8(-4)
	add r20,r25

	mov r30,r20
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	ld  r12,Z
	ldd r13,Z+1
	ldd r14,Z+2
	ldi r20,lo8(4)
	add r20,r25

	mov r30,r20
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	movw r6,r12
	mov r8,r14
	sub r6,r16
	sbc r7,r17
	sbc r8,__zero_reg__
	sbrc r17,7
	inc r8
	st Z,r6
	std Z+1,r7
	std Z+2,r8
	mov r6,__zero_reg__
	ldi r20,lo8(-16)
	mov r7,r20
	clr r8
	dec r8
	rjmp .Llpx4_convert_5
.Llpx4_convert_6:
	; Finish this factor and advance to the next frequency.

	mov r30,r19
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	add r6,r16
	adc r7,r17
	adc r8,__zero_reg__
	sbrc r17,7
	dec r8
	st Z,r6
	std Z+1,r7
	std Z+2,r8
	subi r24,lo8(-(1))
	cpi r24,lo8(10)
	breq .+2
	rjmp .Llpx4_convert_9
	; Recover the output pointer; fold mirrored P/Q terms into LPC.
	ldi r20,lo8(4)
	add r20,r18
	subi r18,lo8(-(28))
	subi r30,4
	ldd r29,Z+3
	subi r30,24
	ldd r28,Z+3
	ldi r21,lo8(4)
	ldi r19,0
.Llpx4_convert_11:

	mov r30,r20
	ldi r31,hi8(_ZN14Lpx4HybridCore6ringQ_E)

	ld r24,Z
	ldd r25,Z+1
	ldd r26,Z+2
	mov r30,r18
	ld r22,Z
	add r24,r22
	ldd r22,Z+1
	adc r25,r22
	ldd r22,Z+2
	adc r26,r22

	; Preserve the original signed coefficient rounding and output rails.
	inc r26
	cpi r26,2
	brsh 1f
	cpi r26,1
	ror r25
	ror r24
	sbrc r26,0
	rjmp 2f
	adc r24,__zero_reg__
	adc r25,__zero_reg__
	cpi r25,128
	brne 2f
	cpi r24,1
	adc r24,__zero_reg__
	rjmp 2f
	1: ldi r24,255
	ldi r25,127
	cpi r26,129
	brlo 2f
	ldi r24,1
	ldi r25,128
	2:

	st Y+,r24
	st Y+,r25
	subi r18,lo8(-(4))
	cpi r19,lo8(4)
	breq .Llpx4_convert_13
	add r20,r21
.Llpx4_convert_10:
	subi r19,lo8(-(1))
	cpi r19,lo8(10)
	breq .+2
	rjmp .Llpx4_convert_11

	pop r29
	pop r28
	pop r14
	pop r8
	pop r7
	pop r6
	pop r4
	pop r3
	ret
.Llpx4_convert_13:
	ldi r21,lo8(-4)
	rjmp .Llpx4_convert_10
	.size lpx4_tiny_convert,.-lpx4_tiny_convert
	.popsection
)LPX4_ASM"
