/* Consume PWM samples at 8 kHz and own the output queue state. */
	.section	.text.__vector_14,"ax",@progbits
.global	__vector_14
	.type	__vector_14, @function
__vector_14:
	push r1
	push r0
	in r0,__SREG__
	push r0
	clr __zero_reg__
	push r24
	push r25
	push r30
	push r31
/* prologue: Signal */
/* frame size = 0 */
/* stack size = 7 */
.L__stack_usage = 7
	lds r24,lpx25_tail
	lds r25,lpx25_head
	cp r25,r24
	breq .L263
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(lpx25_queue))
	sbci r31,hi8(-(lpx25_queue))
	ld r25,Z
	subi r24,lo8(-(1))
	andi r24,lo8(31)
	sts lpx25_tail,r24
.L262:
	mov r24,r25
	ldi r25,0
	sts 136+1,r25
	sts 136,r24
/* epilogue start */
	pop r31
	pop r30
	pop r25
	pop r24
	pop r0
	out __SREG__,r0
	pop r0
	pop r1
	reti
.L263:
	ldi r25,lo8(-128)
	rjmp .L262
	.size	__vector_14, .-__vector_14
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
