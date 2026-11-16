/* Read bits and refill the byte cache from the LPX payload. */
	.section	.text._ZN14Lpx4HybridCore8readBitsEh.constprop.6,"ax",@progbits
	.type	_ZN14Lpx4HybridCore8readBitsEh.constprop.6, @function
_ZN14Lpx4HybridCore8readBitsEh.constprop.6:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	lds r21,_ZN17Lpx4TinyRomPlayer7decoderE+22
	mov r22,r21
	sub r22,r24
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+21
	mov r19,r24
	mov r18,r25
	sbrs r22,7
	rjmp .L35
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+28
	cpse r18,__zero_reg__
	rjmp .L39
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+10
	lds r19,_ZN17Lpx4TinyRomPlayer7decoderE+10+1
	cp r18,__zero_reg__
	cpc r19,__zero_reg__
	brne .L37
	ldi r18,lo8(4)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+28,r18
.L39:
	ldi r20,0
	rjmp .L36
.L37:
	subi r18,1
	sbc r19,__zero_reg__
	sts _ZN17Lpx4TinyRomPlayer7decoderE+10+1,r19
	sts _ZN17Lpx4TinyRomPlayer7decoderE+10,r18
	lds r30,_ZN17Lpx4TinyRomPlayer7decoderE
	lds r31,_ZN17Lpx4TinyRomPlayer7decoderE+1
/* #APP */

	lpm r20,Z+

/* #NOAPP */
	sts _ZN17Lpx4TinyRomPlayer7decoderE+1,r31
	sts _ZN17Lpx4TinyRomPlayer7decoderE,r30
.L36:
	mov r19,r22
	neg r19
	mov r18,r20
/* #APP */

	tst r21
	breq 2f
	1:
	.if 1
	lsl r18
	.else
	lsr r18
	.endif
	dec r21
	brne 1b
	2:

/* #NOAPP */
	or r18,r25
	mov r25,r20
.L35:
/* #APP */

	tst r19
	breq 2f
	1:
	.if 0
	lsl r25
	.else
	lsr r25
	.endif
	dec r19
	brne 1b
	2:

/* #NOAPP */
	sts _ZN17Lpx4TinyRomPlayer7decoderE+21,r25
	andi r22,lo8(7)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+22,r22
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZL8bitMasks))
	sbci r31,hi8(-(_ZL8bitMasks))
/* #APP */

	lpm r24, Z

/* #NOAPP */
	and r24,r18
/* epilogue start */
	ret
	.size	_ZN14Lpx4HybridCore8readBitsEh.constprop.6, .-_ZN14Lpx4HybridCore8readBitsEh.constprop.6
	.section	.text._ZN14Lpx4HybridCore7readOneEv.constprop.5,"ax",@progbits
	.type	_ZN14Lpx4HybridCore7readOneEv.constprop.5, @function
_ZN14Lpx4HybridCore7readOneEv.constprop.5:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	ldi r24,lo8(1)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
/* epilogue start */
	ret
	.size	_ZN14Lpx4HybridCore7readOneEv.constprop.5, .-_ZN14Lpx4HybridCore7readOneEv.constprop.5
