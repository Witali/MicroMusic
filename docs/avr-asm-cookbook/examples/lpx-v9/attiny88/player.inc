/* Own the main decode loop, queue production and playback lifecycle. */
	.section	.text.startup.main,"ax",@progbits
.global	main
	.type	main, @function
main:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	ldi r24,lo8(-128)
	sts 97,r24
	sts 97,__zero_reg__
#include "header.inc"
	mov r14,__zero_reg__
	ldi r25,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+71)
	mov r4,r25
	ldi r25,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+71)
	mov r5,r25
	ldi r18,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+51)
	mov r6,r18
	ldi r18,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+51)
	mov r7,r18
	ldi r19,lo8(-128)
	mov r12,r19
	mov r13,__zero_reg__
.L136:
	lds r24,lpx25_eof
	cpse r24,__zero_reg__
	rjmp .L135
	lds r16,lpx25_head
	ldi r24,lo8(1)
	add r24,r16
	andi r24,lo8(31)
	mov r15,r24
	lds r24,lpx25_tail
	cp r24,r15
	breq .L136
/* #APP */

	.global lpx25_decode_begin
lpx25_decode_begin:

/* #NOAPP */
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+28
	cpse r24,__zero_reg__
	rjmp .L219
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+18
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+20
	cpse r24,r25
	rjmp .L214
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+10
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+10+1
	or r24,r25
	brne .L141
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+21
	tst r24
	breq .L219
.L141:
	ldi r24,lo8(3)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+28,r24
.L219:
	ldi r25,0
.L140:
/* #APP */

	.global lpx25_decode_end
lpx25_decode_end:

/* #NOAPP */
	cpse r25,__zero_reg__
	rjmp .L163
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+28
	sts lpx25_error,r24
.L135:
	ldi r24,lo8(1)
	sts lpx25_eof,r24
	tst r14
	breq .L169
.L170:
	lds r25,lpx25_head
	lds r24,lpx25_tail
	cpse r25,r24
	rjmp .L170
.L169:
	in r24,__SREG__
/* #APP */

	cli

/* #NOAPP */
	out 0x25,__zero_reg__
	sts 110,__zero_reg__
	ldi r25,lo8(1)
	sts lpx25_stopped,r25
	out __SREG__,r24
.L171:
	rjmp .L171
.L178:
	mov r24,r14
.L167:
	mov r14,r24
	rjmp .L136
.L214:
	tst r24
	breq .L142
.L145:
	lds r30,_ZN17Lpx4TinyRomPlayer7decoderE+25
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+23
	sub r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L215
	ldi r24,0
	rjmp .L143
.L142:
	rcall _ZN14Lpx4HybridCore15prepareSubframeEv.constprop.1
	cpse r24,__zero_reg__
	rjmp .L145
	rjmp .L219
.L215:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+24
	cpi r25,lo8(14)
	brne .L146
/* #APP */

	ldi r25,4
	sub r25,r24
	brvc 1f
	lsr r25
	rjmp 2f
	1: asr r25
	2: asr r25
	asr r25
	add r24,r25

/* #NOAPP */
.L147:
	mov __tmp_reg__,r24
	lsl r0
	sbc r25,r25
.L143:
	lds r30,_ZN17Lpx4TinyRomPlayer7decoderE+27
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+329))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+329))
/* #APP */

	ld __tmp_reg__,Z
	dec __tmp_reg__
	st Z,__tmp_reg__
	brpl .L148

/* #NOAPP */
	rjmp .L220
.L146:
	tst r25
	breq .L174
/* #APP */

	ldi r18,4
	mov r19,r25
	.if 1
	lsr r19
	.endif
	.rept 4-1
	lsr r19
	brcc 1f
	add r18,r24
	1: ror r18
	.endr
	.if !1
	sbrc r19,0
	add r18,r24
	.endif
	swap r25
	andi r25,240
	sbrc r24,7
	sub r18,r25

/* #NOAPP */
	mov r24,r18
	rjmp .L147
.L174:
	ldi r24,0
	rjmp .L147
.L148:
	mov r22,r24
.L150:
	lds r30,_ZN17Lpx4TinyRomPlayer7decoderE+25
	ldi r24,lo8(1)
	add r24,r30
	sts _ZN17Lpx4TinyRomPlayer7decoderE+25,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+73))
	st Z,r22
	lds r20,_ZN17Lpx4TinyRomPlayer7decoderE+14
	lds r21,_ZN17Lpx4TinyRomPlayer7decoderE+14+1
	ldi r24,0
	ldi r25,0
	movw r26,r24
	tst r22
	breq .L153
	movw r24,r20
	ldi r27,0
	ldi r26,0
	cpi r22,lo8(1)
	breq .L153
	ldi r27,0
	ldi r26,0
	cpi r22,lo8(-1)
	breq .L218
	cpi r22,lo8(3)
	breq .L156
	cpi r22,lo8(-3)
	breq .+2
	rjmp .L157
.L156:
	movw r24,r20
	ldi r27,0
	ldi r26,0
/* #APP */

	lsl r24
	rol r25
	rol r26
	add r24,r20
	adc r25,r21
	adc r26,__zero_reg__

/* #NOAPP */
	sbrs r22,7
	rjmp .L153
.L218:
	com r27
	com r26
	com r25
	neg r24
	sbci r25,lo8(-1)
	sbci r26,lo8(-1)
	sbci r27,lo8(-1)
.L153:
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+52
	subi r18,lo8(-(-127))
	ldi r28,lo8(1)
	cpi r18,lo8(2)
	brlo .L159
	ldi r28,0
.L159:
	movw r8,r24
	movw r10,r26
#include "lpc-synthesis.inc"
#include "postfilter-pwm.inc"
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+18
	subi r24,lo8(-(1))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+18,r24
	cpi r24,lo8(20)
	brne .L176
	sts _ZN17Lpx4TinyRomPlayer7decoderE+18,__zero_reg__
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+12
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+12+1
	sbiw r24,20
	sts _ZN17Lpx4TinyRomPlayer7decoderE+12+1,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+12,r24
	cpi r24,20
	cpc r25,__zero_reg__
	brlo .L162
	ldi r24,lo8(20)
	ldi r25,0
.L162:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+20,r24
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+19
	subi r24,lo8(-(1))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+19,r24
.L176:
	ldi r25,lo8(1)
	rjmp .L140
.L220:
	lds r30,_ZN17Lpx4TinyRomPlayer7decoderE+27
	ldi r25,lo8(1)
	add r25,r30
	sts _ZN17Lpx4TinyRomPlayer7decoderE+27,r25
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+333))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+333))
	ld r22,Z
	add r22,r24
	cpi r22,lo8(32)
	brlt .L151
	ldi r22,lo8(31)
	rjmp .L150
.L151:
	cpi r22,lo8(-32)
	brlt .+2
	rjmp .L150
	ldi r22,lo8(-32)
	rjmp .L150
.L157:
	lsr r21
	ror r20
	lsr r21
	ror r20
/* #APP */

	mov r24,r22
	clr r25
	clr r26
	lsr r24
	.rept 6
	brcc 1f
	add r25,r20
	adc r26,r21
	1: ror r26
	ror r25
	ror r24
	.endr
	.if 1
	sbrs r22,7
	rjmp 2f
	.if 6 == 6
	dec r24
	.endif
	sub r25,r20
	sbc r26,r21
	2:
	.endif
	.if 0
	sbrc r21,7
	sub r26,r22
	.endif
	mov r27,r26
	lsl r27
	sbc r27,r27

/* #NOAPP */
	rjmp .L153
.L163:
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+18
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+20
	cpse r18,r24
	rjmp .L177
	ldi r24,lo8(1)
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+28
	cpse r18,__zero_reg__
.L177:
	ldi r24,0
.L164:
	mov r30,r16
	ldi r31,0
	subi r30,lo8(-(lpx25_queue))
	sbci r31,hi8(-(lpx25_queue))
	st Z,r28
	in r18,__SREG__
/* #APP */

	cli

/* #NOAPP */
	sts lpx25_head,r15
	tst r24
	breq .L166
	ldi r19,lo8(1)
	sts lpx25_eof,r19
.L166:
	out __SREG__,r18
	cpse r14,__zero_reg__
	rjmp .L178
	ldi r20,lo8(24)
	cp r15,r20
	breq .L168
	tst r24
	brne .+2
	rjmp .L167
.L168:
	sbi 0x4,1
	sts 136+1,r13
	sts 136,r12
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
	ldi r24,lo8(10)
	out 0x25,r24
/* #APP */

	sei

/* #NOAPP */
	mov r24,r25
	rjmp .L167
	.size	main, .-main
