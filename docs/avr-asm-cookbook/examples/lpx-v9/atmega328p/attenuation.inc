/* Apply bounded Q14 attenuation for the two output filters. */
	.section	.text._ZL16lpx4AttenuateQ14ji,"ax",@progbits
	.type	_ZL16lpx4AttenuateQ14ji, @function
_ZL16lpx4AttenuateQ14ji:
	push r16
	push r17
/* prologue: function */
/* frame size = 0 */
/* stack size = 2 */
.L__stack_usage = 2
	movw r20,r24
/* #APP */

	clr r24
	muls r21,r23
	movw r18,r0
	mul r20,r22
	movw r16,r0
	mulsu r21,r22
	add r17,r0
	adc r18,r1
	adc r19,r24
	mulsu r23,r20
	sbc r19,r24
	add r17,r0
	adc r18,r1
	adc r19,r24
	.rept 2
	lsl r17
	rol r18
	rol r19
	.endr
	movw r24,r18
	clr __zero_reg__

/* epilogue start */
/* #NOAPP */
	pop r17
	pop r16
	ret
	.size	_ZL16lpx4AttenuateQ14ji, .-_ZL16lpx4AttenuateQ14ji
