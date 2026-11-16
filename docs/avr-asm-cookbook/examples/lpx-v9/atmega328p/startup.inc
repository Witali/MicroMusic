/* Reset the decoder, initialize playback state and stop the timers. */
	.section	.text.unlikely._ZL4stopv,"ax",@progbits
	.type	_ZL4stopv, @function
_ZL4stopv:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	out 0x24,__zero_reg__
	out 0x25,__zero_reg__
	sts 110,__zero_reg__
	ldi r24,lo8(1)
	sts lpx25_stopped,r24
/* epilogue start */
	ret
	.size	_ZL4stopv, .-_ZL4stopv
	.section	.text._ZN14Lpx4HybridCore10resetStateEv.constprop.14,"ax",@progbits
	.type	_ZN14Lpx4HybridCore10resetStateEv.constprop.14, @function
_ZN14Lpx4HybridCore10resetStateEv.constprop.14:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	ldi r30,lo8(_ZL7decoder+14)
	ldi r31,hi8(_ZL7decoder+14)
	ldi r24,lo8(86)
	ldi r25,lo8(1)
	movw r26,r30
	movw r18,r24
	0:
	st X+,__zero_reg__
	subi r18,1
	sbci r19,0
	brne 0b
/* epilogue start */
	ret
	.size	_ZN14Lpx4HybridCore10resetStateEv.constprop.14, .-_ZN14Lpx4HybridCore10resetStateEv.constprop.14
	.section	.text.startup._GLOBAL__sub_I_lpx25_queue,"ax",@progbits
	.type	_GLOBAL__sub_I_lpx25_queue, @function
_GLOBAL__sub_I_lpx25_queue:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	ldi r30,lo8(_ZL7decoder)
	ldi r31,hi8(_ZL7decoder)
	std Z+1,__zero_reg__
	st Z,__zero_reg__
	std Z+3,__zero_reg__
	std Z+2,__zero_reg__
	std Z+5,__zero_reg__
	std Z+4,__zero_reg__
	std Z+7,__zero_reg__
	std Z+6,__zero_reg__
	std Z+9,__zero_reg__
	std Z+8,__zero_reg__
	std Z+11,__zero_reg__
	std Z+10,__zero_reg__
	std Z+13,__zero_reg__
	std Z+12,__zero_reg__
	call _ZN14Lpx4HybridCore10resetStateEv.constprop.14
/* epilogue start */
	ret
	.size	_GLOBAL__sub_I_lpx25_queue, .-_GLOBAL__sub_I_lpx25_queue
	.global __do_global_ctors
	.section .ctors,"a",@progbits
	.p2align	1
	.word	gs(_GLOBAL__sub_I_lpx25_queue)
