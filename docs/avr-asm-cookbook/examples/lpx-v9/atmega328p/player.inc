/* Own the main decode loop, queue production and playback lifecycle. */
	.section	.text.startup.main,"ax",@progbits
.global	main
	.type	main, @function
main:
	ldi r26,lo8(8)
	ldi r27,0
	ldi r30,lo8(gs(1f))
	ldi r31,hi8(gs(1f))
	jmp __prologue_saves__+((18 - 18) * 2)
1:
/* prologue: function */
/* frame size = 8 */
/* stack size = 26 */
.L__stack_usage = 26
	ldi r24,lo8(-128)
	sts 97,r24
	sts 97,__zero_reg__
	call _ZN14Lpx4HybridCore5beginEPKhj.constprop.13
	mov r10,r24
	cpse r24,__zero_reg__
	rjmp .L175
	lds r24,_ZL7decoder+29
	sts lpx25_error,r24
	ldi r24,lo8(1)
	sts lpx25_stopped,r24
.L72:
	rjmp .L72
.L189:
	mov r24,r11
.L166:
	mov r11,r24
.L76:
	lds r24,lpx25_eof
	tst r24
	breq .L73
.L74:
	lds r25,lpx25_head
	lds r24,lpx25_tail
	cpse r25,r24
	rjmp .L74
	in r18,__SREG__
	std Y+1,r18
/* #APP */

	cli

/* #NOAPP */
	call _ZL4stopv
	ldd r19,Y+1
	out __SREG__,r19
.L75:
	rjmp .L75
.L175:
	mov r11,__zero_reg__
	clr r2
	inc r2
	ldi r17,lo8(_ZL7decoder+72)
	mov r8,r17
	ldi r17,hi8(_ZL7decoder+72)
	mov r9,r17
	ldi r16,lo8(_ZL7decoder+52)
	mov r14,r16
	ldi r16,hi8(_ZL7decoder+52)
	mov r15,r16
	ldi r24,lo8(_ZL7decoder+346)
	mov r12,r24
	ldi r24,hi8(_ZL7decoder+346)
	mov r13,r24
	rjmp .L76
.L73:
	lds r3,lpx25_head
	ldi r24,lo8(1)
	add r24,r3
	andi r24,lo8(31)
	std Y+2,r24
	lds r24,lpx25_tail
	ldd r20,Y+2
	cp r24,r20
	breq .L76
	lds r25,_ZL7decoder+18
	lds r24,_ZL7decoder+20
	cpse r25,r24
	rjmp .L77
	lds r24,_ZL7decoder+29
	cpse r24,__zero_reg__
	rjmp .L77
	dec r2
	call _ZN14Lpx4HybridCore5beginEPKhj.constprop.13
	cpse r24,__zero_reg__
	rjmp .L77
.L260:
	lds r24,_ZL7decoder+29
	sts lpx25_error,r24
	in r18,__SREG__
	std Y+1,r18
/* #APP */

	cli

/* #NOAPP */
	ldi r24,lo8(1)
	sts lpx25_eof,r24
	tst r11
	breq .L168
	lds r25,lpx25_head
	lds r24,lpx25_tail
	cpse r25,r24
	rjmp .L169
.L168:
	call _ZL4stopv
.L169:
	ldd r19,Y+1
	out __SREG__,r19
	tst r11
	breq .L170
.L171:
	lds r25,lpx25_head
	lds r24,lpx25_tail
	cpse r25,r24
	rjmp .L171
	in r20,__SREG__
	std Y+1,r20
/* #APP */

	cli

/* #NOAPP */
	call _ZL4stopv
	ldd r24,Y+1
	out __SREG__,r24
.L170:
.L253:
	rjmp .L253
.L77:
/* #APP */

	.global lpx25_decode_begin
lpx25_decode_begin:

/* #NOAPP */
	lds r24,_ZL7decoder+29
	cpse r24,__zero_reg__
	rjmp .L258
	lds r24,_ZL7decoder+18
	lds r25,_ZL7decoder+20
	cpse r24,r25
	rjmp .L249
	lds r24,_ZL7decoder+2
	lds r25,_ZL7decoder+2+1
	or r24,r25
	brne .L84
	lds r24,_ZL7decoder+21
	tst r24
	breq .L258
.L84:
	ldi r24,lo8(3)
	sts _ZL7decoder+29,r24
.L258:
	ldi r25,0
.L82:
/* #APP */

	.global lpx25_decode_end
lpx25_decode_end:

/* #NOAPP */
	tst r25
	brne .+2
	rjmp .L260
	lds r18,_ZL7decoder+18
	lds r24,_ZL7decoder+20
	cpse r18,r24
	rjmp .L188
	lds r24,_ZL7decoder+29
	cpse r24,__zero_reg__
	rjmp .L188
	ldi r24,lo8(1)
	cpse r2,r24
.L188:
	ldi r24,0
.L163:
	mov r30,r3
	ldi r31,0
	subi r30,lo8(-(lpx25_queue))
	sbci r31,hi8(-(lpx25_queue))
	ldd r26,Y+3
	st Z,r26
	in r18,__SREG__
/* #APP */

	cli

/* #NOAPP */
	ldd r27,Y+2
	sts lpx25_head,r27
	tst r24
	breq .L165
	ldi r30,lo8(1)
	sts lpx25_eof,r30
.L165:
	out __SREG__,r18
	cpse r11,__zero_reg__
	rjmp .L189
	ldd r31,Y+2
	cpi r31,lo8(24)
	breq .L167
	tst r24
	brne .+2
	rjmp .L166
.L167:
	sbi 0x4,1
	ldi r18,lo8(-128)
	ldi r19,0
	sts 136+1,r19
	sts 136,r18
	ldi r24,lo8(-127)
	sts 128,r24
	ldi r24,lo8(9)
	sts 129,r24
	ldi r24,lo8(-7)
	out 0x27,r24
	out 0x26,__zero_reg__
	ldi r24,lo8(2)
	out 0x15,r24
	sts 110,r24
	out 0x24,r24
	out 0x25,r24
/* #APP */

	sei

/* #NOAPP */
	mov r24,r25
	rjmp .L166
#include "subframes.inc"
.L86:
	lds r19,_ZL7decoder+28
	std Y+1,r19
	lds r20,_ZL7decoder+27
	std Y+4,r20
	call _ZNK14Lpx4HybridCore12pitchPredictEv.constprop.10
	ldd r25,Y+1
	ldd r26,Y+4
	cp r25,r26
	brsh .+2
	rjmp .L146
.L151:
	lds r30,_ZL7decoder+25
	ldi r25,lo8(1)
	add r25,r30
	sts _ZL7decoder+25,r25
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+74))
	sbci r31,hi8(-(_ZL7decoder+74))
	st Z,r24
	lds r18,_ZL7decoder+14
	lds r19,_ZL7decoder+14+1
	mov r20,r24
/* #APP */

	mulsu r20,r18
	movw r4,r0
	mov r6,r1
	lsl r6
	sbc r6,r6
	mulsu r20,r19
	add r5,r0
	adc r6,r1
	mov r7,r6
	lsl r7
	sbc r7,r7
	clr __zero_reg__

/* #NOAPP */
#include "lpc-synthesis.inc"
#include "postfilter-pwm.inc"
	lds r24,_ZL7decoder+18
	subi r24,lo8(-(1))
	cpi r24,lo8(20)
	breq .L160
	sts _ZL7decoder+18,r24
.L259:
	mov r25,r10
	rjmp .L82
.L143:
	sts _ZL7decoder+31,r24
	ldd r25,Y+5
	ldd r24,Y+6
	std Y+6,r17
	std Y+5,r16
	mov r16,r25
	mov r17,r24
	rjmp .L144
.L146:
	ldd r27,Y+1
	mov r18,r27
	ldi r19,0
	subi r18,lo8(-(_ZL7decoder))
	sbci r19,hi8(-(_ZL7decoder))
	movw r30,r18
	subi r30,-74
	sbci r31,-2
	ld r25,Z
	cpse r25,__zero_reg__
	rjmp .L148
	subi r27,lo8(-(1))
	sts _ZL7decoder+28,r27
	subi r18,-77
	sbci r19,-2
	movw r30,r18
	ld r25,Z
	add r24,r25
.L149:
	lds r25,_ZL7decoder+29
	cpse r25,__zero_reg__
	rjmp .L258
	cpi r24,lo8(32)
	brlt .L150
	ldi r24,lo8(31)
.L150:
	cpi r24,lo8(-32)
	brlt .+2
	rjmp .L151
	ldi r24,lo8(-32)
	rjmp .L151
.L148:
	subi r25,lo8(-(-1))
	st Z,r25
	rjmp .L149
.L160:
	sts _ZL7decoder+18,__zero_reg__
	lds r24,_ZL7decoder+6
	lds r25,_ZL7decoder+6+1
	sbiw r24,20
	sts _ZL7decoder+6+1,r25
	sts _ZL7decoder+6,r24
	cpi r24,20
	cpc r25,__zero_reg__
	brlo .L161
	ldi r24,lo8(20)
	ldi r25,0
.L161:
	sts _ZL7decoder+20,r24
	lds r25,_ZL7decoder+19
	ldi r24,lo8(1)
	add r24,r25
	andi r24,lo8(7)
	andi r25,lo8(8)
	or r24,r25
	sts _ZL7decoder+19,r24
	rjmp .L259
.L95:
	ldd r27,Y+4
	mov r26,r27
	ldi r27,0
	mov r0,r7
	rjmp 2f
	1:
	lsl r26
	rol r27
	2:
	dec r0
	brpl 1b
	std Y+6,r27
	std Y+5,r26
	ldi r24,0
	tst r7
	breq .L173
	mov r24,r7
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
.L173:
	ldd r25,Y+5
	or r24,r25
.L96:
	mov r18,r24
	ldi r19,0
	sbrs r24,0
	rjmp .L99
	subi r18,-1
	sbci r19,-1
	asr r19
	ror r18
	neg r18
.L100:
	ldi r25,lo8(1)
	add r25,r6
	add r24,r25
	tst r5
	breq .L102
	movw r26,r16
	ld r24,X
	subi r24,lo8(-(-1))
	add r24,r18
.L102:
	lds r25,_ZL7decoder+29
	cpse r25,__zero_reg__
	rjmp .L258
	cp r6,r24
	brlt .+2
	rjmp .L84
	cp r24,r4
	brlo .+2
	rjmp .L84
	ldi r18,lo8(1)
	add r18,r24
	lds r25,_ZL7decoder+30
	sbrs r25,0
	rjmp .L103
	movw r30,r16
	ld r19,Z
	cp r18,r19
	breq .L103
	andi r25,lo8(~(1<<2))
	sts _ZL7decoder+30,r25
.L103:
	movw r26,r16
	adiw r26,10
	st X,r18
	subi r16,-1
	sbci r17,-1
	mov r6,r24
	ldi r27,hi8(_ZL7decoder+346)
	cpi r16,lo8(_ZL7decoder+346)
	cpc r17,r27
	breq .+2
	rjmp .L104
	rjmp .L89
.L252:
	lds r18,_ZL7decoder+331
	sts _ZL7decoder+332,r18
	lds r18,_ZL7decoder+334
	sts _ZL7decoder+335,r18
	cpse r17,__zero_reg__
	rjmp .L133
	sts _ZL7decoder+331,r25
	lds r25,_ZL7decoder+333
	sts _ZL7decoder+334,r25
.L133:
	mov r18,r17
	ldi r19,0
	subi r18,lo8(-(_ZL7decoder))
	sbci r19,hi8(-(_ZL7decoder))
	movw r30,r18
	subi r30,-74
	sbci r31,-2
	ldd r20,Y+1
	st Z,r20
	subi r18,-77
	sbci r19,-2
	movw r26,r18
	st X,r24
	ldi r24,lo8(3)
	sts _ZL7decoder+27,r24
	rjmp .L128
	.size	main, .-main
