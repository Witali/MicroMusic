/* Consume PWM samples at 8 kHz and own the output queue state. */
	.section	.text.__vector_12,"ax",@progbits
.global	__vector_12
	.type	__vector_12, @function
__vector_12:
/* prologue: naked */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
/* #APP */

	in r3,63
	push r30
	push r31
	lds r2,lpx25_head
	lds r30,lpx25_tail
	cp r2,r30
	breq 2f
	ldi r31,hi8(lpx25_queue)
	ori r30,lo8(lpx25_queue)
	ld r2,Z
	inc r30
	andi r30,31
	sts lpx25_tail,r30
	rjmp 3f
	2: ldi r30,128
	mov r2,r30
	3:
	sts 136,r2
	pop r31
	pop r30
	out 63,r3
	reti

/* epilogue start */
/* #NOAPP */
	.size	__vector_12, .-__vector_12
	.section	.bss.lpx25_queue,"aw",@nobits
	.p2align	5
	.type	lpx25_queue, @object
	.size	lpx25_queue, 32
lpx25_queue:
	.zero	32
	.section	.bss.lpx25_tail,"aw",@nobits
	.type	lpx25_tail, @object
	.size	lpx25_tail, 1
lpx25_tail:
	.zero	1
	.section	.bss.lpx25_head,"aw",@nobits
	.type	lpx25_head, @object
	.size	lpx25_head, 1
lpx25_head:
	.zero	1
	.section	.bss.lpx25_eof,"aw",@nobits
	.type	lpx25_eof, @object
	.size	lpx25_eof, 1
lpx25_eof:
	.zero	1
	.section	.bss.lpx25_stopped,"aw",@nobits
	.type	lpx25_stopped, @object
	.size	lpx25_stopped, 1
lpx25_stopped:
	.zero	1
	.section	.bss.lpx25_error,"aw",@nobits
	.type	lpx25_error, @object
	.size	lpx25_error, 1
lpx25_error:
	.zero	1
