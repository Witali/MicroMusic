/* Read bits and refill the byte cache from the LPX payload. */
	.section	.text._ZN14Lpx4HybridCore8readByteEv.constprop.16,"ax",@progbits
	.type	_ZN14Lpx4HybridCore8readByteEv.constprop.16, @function
_ZN14Lpx4HybridCore8readByteEv.constprop.16:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	lds r24,_ZL7decoder+29
	cpse r24,__zero_reg__
	rjmp .L4
	lds r24,_ZL7decoder+2
	lds r25,_ZL7decoder+2+1
	sbiw r24,0
	brne .L3
	ldi r24,lo8(4)
	sts _ZL7decoder+29,r24
.L4:
	ldi r24,0
/* epilogue start */
	ret
.L3:
	sbiw r24,1
	sts _ZL7decoder+2+1,r25
	sts _ZL7decoder+2,r24
	lds r30,_ZL7decoder
	lds r31,_ZL7decoder+1
	movw r24,r30
	adiw r24,1
	sts _ZL7decoder+1,r25
	sts _ZL7decoder,r24
/* #APP */

	lpm r24, Z

/* #NOAPP */
	ret
	.size	_ZN14Lpx4HybridCore8readByteEv.constprop.16, .-_ZN14Lpx4HybridCore8readByteEv.constprop.16
	.section	.text._ZN14Lpx4HybridCore6read16Ev.constprop.15,"ax",@progbits
	.type	_ZN14Lpx4HybridCore6read16Ev.constprop.15, @function
_ZN14Lpx4HybridCore6read16Ev.constprop.15:
	push r28
/* prologue: function */
/* frame size = 0 */
/* stack size = 1 */
.L__stack_usage = 1
	call _ZN14Lpx4HybridCore8readByteEv.constprop.16
	mov r28,r24
	call _ZN14Lpx4HybridCore8readByteEv.constprop.16
	mov r25,r24
	mov r24,r28
/* epilogue start */
	pop r28
	ret
	.size	_ZN14Lpx4HybridCore6read16Ev.constprop.15, .-_ZN14Lpx4HybridCore6read16Ev.constprop.15
	.section	.text._ZN14Lpx4HybridCore8readBitsEh.constprop.6,"ax",@progbits
	.type	_ZN14Lpx4HybridCore8readBitsEh.constprop.6, @function
_ZN14Lpx4HybridCore8readBitsEh.constprop.6:
	push r28
	push r29
/* prologue: function */
/* frame size = 0 */
/* stack size = 2 */
.L__stack_usage = 2
	lds r29,_ZL7decoder+22
	cp r29,r24
	brlo .L10
	lds r18,_ZL7decoder+21
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZL8bitMasks))
	sbci r31,hi8(-(_ZL8bitMasks))
/* #APP */

	lpm r30, Z

/* #NOAPP */
	and r30,r18
	ldi r19,0
	mov r0,r24
	rjmp 2f
	1:
	asr r19
	ror r18
	2:
	dec r0
	brpl 1b
	sts _ZL7decoder+21,r18
	sub r29,r24
	sts _ZL7decoder+22,r29
.L9:
	mov r24,r30
/* epilogue start */
	pop r29
	pop r28
	ret
.L10:
	mov r28,r24
	call _ZN14Lpx4HybridCore8readByteEv.constprop.16
	mov r25,r28
	sub r25,r29
	mov r30,r25
	ldi r31,0
	subi r30,lo8(-(_ZL8bitMasks))
	sbci r31,hi8(-(_ZL8bitMasks))
/* #APP */

	lpm r30, Z

/* #NOAPP */
	and r30,r24
	rjmp 2f
	1:
	lsl r30
	2:
	dec r29
	brpl 1b
	lds r18,_ZL7decoder+21
	or r30,r18
	mov r18,r24
	ldi r19,0
	mov r0,r25
	rjmp 2f
	1:
	asr r19
	ror r18
	2:
	dec r0
	brpl 1b
	sts _ZL7decoder+21,r18
	ldi r24,lo8(8)
	sub r24,r25
	sts _ZL7decoder+22,r24
	rjmp .L9
	.size	_ZN14Lpx4HybridCore8readBitsEh.constprop.6, .-_ZN14Lpx4HybridCore8readBitsEh.constprop.6
	.section	.text._ZN14Lpx4HybridCore7readOneEv.constprop.5,"ax",@progbits
	.type	_ZN14Lpx4HybridCore7readOneEv.constprop.5, @function
_ZN14Lpx4HybridCore7readOneEv.constprop.5:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	ldi r24,lo8(1)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
/* epilogue start */
	ret
	.size	_ZN14Lpx4HybridCore7readOneEv.constprop.5, .-_ZN14Lpx4HybridCore7readOneEv.constprop.5
