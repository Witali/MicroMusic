/* Predict excitation from the delayed quantized sample. */
	.section	.text._ZNK14Lpx4HybridCore12pitchPredictEv.constprop.10,"ax",@progbits
	.type	_ZNK14Lpx4HybridCore12pitchPredictEv.constprop.10, @function
_ZNK14Lpx4HybridCore12pitchPredictEv.constprop.10:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	lds r30,_ZL7decoder+25
	lds r24,_ZL7decoder+23
	sub r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	ld r18,Z
	tst r18
	breq .L8
	lds r19,_ZL7decoder+24
/* #APP */

	muls r18,r19
	movw r24,r0
	clr __zero_reg__
	subi r24,248
	sbci r25,255
	swap r24
	andi r24,15
	swap r25
	andi r25,240
	or r24,r25

/* #NOAPP */
	mov __tmp_reg__,r24
	lsl r0
	sbc r25,r25
	ret
.L8:
	ldi r25,0
	ldi r24,0
/* epilogue start */
	ret
	.size	_ZNK14Lpx4HybridCore12pitchPredictEv.constprop.10, .-_ZNK14Lpx4HybridCore12pitchPredictEv.constprop.10
