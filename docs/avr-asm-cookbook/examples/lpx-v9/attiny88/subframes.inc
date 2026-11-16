/* Parse frames and pulse packets and select LPC anchors. */
	.section	.text._ZN14Lpx4HybridCore15prepareSubframeEv.constprop.1,"ax",@progbits
	.type	_ZN14Lpx4HybridCore15prepareSubframeEv.constprop.1, @function
_ZN14Lpx4HybridCore15prepareSubframeEv.constprop.1:
	ldi r27,0
	ldi r26,0
	ldi r30,lo8(gs(1f))
	ldi r31,hi8(gs(1f))
	rjmp __prologue_saves__+((18 - 12) * 2)
1:
/* prologue: function */
/* frame size = 0 */
/* stack size = 12 */
.L__stack_usage = 12
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+19
	mov r25,r24
	andi r25,lo8(7)
	brne .+2
	rjmp .L42
.L46:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+19
	sbrs r25,0
	rjmp .L43
.L44:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+19
	mov r19,r25
	andi r19,lo8(7)
	mov r15,r19
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+30
	mov r28,r24
	ldi r29,0
	lsl r28
	rol r29
	subi r28,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+356))
	sbci r29,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+356))
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+29
	sbrc r18,2
	rjmp .L67
	ldi r18,lo8(10)
	eor r24,r18
	mov r16,r24
	ldi r17,0
	lsl r16
	rol r17
	subi r16,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+356))
	sbci r17,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+356))
	andi r25,lo8(3)
	brne .L86
	sts _ZN17Lpx4TinyRomPlayer7decoderE+30,r24
	mov r24,r15
	lsr r24
	lsr r24
	subi r24,lo8(-(1))
	movw r22,r16
	lsl r24
	lsl r24
	lsl r24
	rcall _ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10
	mov r25,r28
	mov r24,r29
	movw r28,r16
	mov r16,r25
	mov r17,r24
.L86:
	mov r24,r15
	lsl r24
	subi r24,lo8(-(1))
	andi r24,lo8(7)
	movw r30,r16
	ldi r26,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+31)
	ldi r27,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+31)
	movw r22,r28
	subi r22,-20
	sbci r23,-1
.L87:
	ld r12,Y+
	ld r13,Y+
	ld r20,Z+
	ld r21,Z+
	mov r25,r24
/* #APP */

	clt
	movw r18,r12
	sub r18,r20
	sbc r19,r21
	brge 1f
	set
	com r19
	neg r18
	sbci r19,255
	1: movw r16,r18
	lsr r17
	ror r16
	lsr r25
	.rept 3-1
	lsr r25
	brcc 2f
	add r16,r18
	adc r17,r19
	2: ror r17
	ror r16
	.endr
	brtc 3f
	com r17
	neg r16
	sbci r17,255
	3: add r16,r20
	adc r17,r21

/* #NOAPP */
	st X+,r16
	st X+,r17
	cp r22,r28
	cpc r23,r29
	breq .+2
	rjmp .L87
	rjmp .L84
.L42:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+29
	ori r25,lo8(1<<2)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+29,r25
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+26
	andi r24,lo8(8)
	sbrs r25,3
	rjmp .L45
	cpse r24,__zero_reg__
	rjmp .L46
.L47:
	ldi r28,lo8(6)
	sbrs r25,1
	ldi r28,lo8(5)
.L49:
	rcall _ZN14Lpx4HybridCore7readOneEv.constprop.5
	cpse r24,__zero_reg__
	rjmp .L50
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+29
	sbrc r24,0
	rjmp .L48
.L54:
	ldi r24,lo8(3)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+28,r24
.L61:
	ldi r24,0
	rjmp .L41
.L45:
	tst r24
	breq .L47
.L48:
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+29
	sbrc r24,0
	rjmp .L64
	ori r24,lo8(4)
	ori r24,lo8(1<<0)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+29,r24
.L64:
	ldi r24,lo8(8)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r29,r24
	mov r28,r24
	andi r28,lo8(31)
	swap r24
	andi r24,lo8(14)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+24,r24
	tst r24
	brne .+2
	rjmp .L90
	ldi r24,lo8(7)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	subi r24,lo8(-(18))
.L65:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+23,r24
	mov r20,r28
	ldi r21,0
	ldi r24,lo8(43)
	ldi r25,lo8(23)
	sbrc r29,0
	rjmp .L66
	ldi r24,lo8(98)
	ldi r25,lo8(16)
.L66:
	asr r21
	ror r20
	ldi r18,lo8(12)
	sub r18,r20
/* #APP */

	tst r18
	brmi 3f
	rjmp 2f
	1: lsr r25
	ror r24
	2: dec r18
	brpl 1b
	rjmp 4f
	3: lsl r24
	rol r25
	inc r18
	brmi 3b
	4:

/* #NOAPP */
	adiw r24,8
	andi r24,240
	sts _ZN17Lpx4TinyRomPlayer7decoderE+14+1,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+14,r24
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+28
	cpse r24,__zero_reg__
	rjmp .L61
	rjmp .L46
.L50:
	rcall _ZN14Lpx4HybridCore7readOneEv.constprop.5
	mov r12,r24
	ldi r24,lo8(1)
	cpse r12,__zero_reg__
	rjmp .L115
	ldi r24,0
.L53:
	ldi r25,lo8(-4)
	add r25,r28
	mov r14,r25
	sub r14,r24
	mov r13,r24
	add r13,r28
	lds r15,_ZN17Lpx4TinyRomPlayer7decoderE+26
	mov r18,r15
	andi r18,lo8(2)
	mov r15,r18
	inc r15
	inc r15
	swap r15
	ldi r30,lo8(-16)
	and r15,r30
	clr r11
	inc r11
	mov r0,r14
	rjmp 2f
	1:
	lsl r11
	2:
	dec r0
	brpl 1b
	ldi r28,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+336)
	ldi r29,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+336)
	ldi r16,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+346)
	ldi r17,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+346)
	mov r10,__zero_reg__
.L63:
	ldi r23,lo8(8)
	mov r9,r23
	mov r8,__zero_reg__
.L58:
	rcall _ZN14Lpx4HybridCore7readOneEv.constprop.5
	tst r24
	breq .L55
	ldi r24,0
	tst r14
	breq .L56
	mov r24,r14
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
.L56:
	or r24,r8
.L57:
	ldd r18,Y+10
	tst r12
	breq .L59
	mov r25,r24
	andi r25,lo8(1)
	neg r25
	lsr r24
	eor r24,r25
	add r24,r18
.L60:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+28
	cpse r25,__zero_reg__
	rjmp .L61
	cp r10,r24
	brlo .+2
	rjmp .L54
	cp r15,r24
	brsh .+2
	rjmp .L54
	st Y+,r18
	cp r18,r24
	breq .L62
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+29
	andi r25,lo8(~(1<<2))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+29,r25
.L62:
	std Y+9,r24
	mov r10,r24
	cp r16,r28
	cpc r17,r29
	brne .L63
	rjmp .L48
.L115:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+29
	sbrc r25,0
	rjmp .L53
	rjmp .L54
.L55:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+28
	cpse r25,__zero_reg__
	rjmp .L57
	add r8,r11
	dec r9
	cpse r9,__zero_reg__
	rjmp .L58
	mov r24,r13
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	rjmp .L57
.L59:
	ldi r25,lo8(1)
	add r25,r10
	add r24,r25
	rjmp .L60
.L90:
	ldi r24,lo8(18)
	rjmp .L65
.L43:
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+26
	sbrs r24,3
	rjmp .L69
	sbrc r25,1
	rjmp .L44
	ldi r24,lo8(7)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r25,r24
	andi r25,lo8(63)
/* #APP */

	mov r18,r25
	lsr r18
	lsr r18
	adc r25,r18

/* #NOAPP */
	sts _ZN17Lpx4TinyRomPlayer7decoderE+329,r25
	sbrs r24,6
	rjmp .L92
	ldi r24,lo8(7)
.L70:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+333,r24
	ldi r24,lo8(127)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+330,r24
	sts _ZN17Lpx4TinyRomPlayer7decoderE+27,__zero_reg__
.L117:
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+28
	tst r24
	brne .+2
	rjmp .L44
	rjmp .L61
.L92:
	ldi r24,lo8(-8)
	rjmp .L70
.L69:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+27,__zero_reg__
	sbrs r24,1
	rjmp .L73
	ldi r24,lo8(4)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r28,r24
	ldi r24,lo8(5)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	cpi r24,lo8(25)
	brlo .+2
	rjmp .L54
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZL9pulseHigh))
	sbci r31,hi8(-(_ZL9pulseHigh))
/* #APP */

	lpm r30, Z

/* #NOAPP */
	mov r24,r28
	andi r24,lo8(3)
	mov r25,r30
	andi r25,lo8(28)
	or r24,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+329,r24
	lsr r30
	lsr r30
	lsr r30
	andi r30,lo8(28)
	lsr r28
	lsr r28
	or r30,r28
	subi r30,lo8(-(20))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+330,r30
	ldi r24,lo8(8)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r25,r24
	andi r25,lo8(15)
	ldi r18,lo8(8)
	eor r25,r18
	subi r25,lo8(-(-8))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+333,r25
	swap r24
	andi r24,lo8(15)
	eor r24,r18
.L118:
	subi r24,lo8(-(-8))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+334,r24
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+26
	sbrc r24,7
	rjmp .L75
.L119:
	ldi r30,lo8(2)
	rjmp .L76
.L73:
	ldi r24,lo8(5)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r28,r24
	ldi r24,lo8(5)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r25,r28
	andi r25,lo8(15)
/* #APP */

	mov r18,r25
	lsr r18
	lsr r18
	adc r25,r18

/* #NOAPP */
	sts _ZN17Lpx4TinyRomPlayer7decoderE+329,r25
	mov r25,r24
	andi r25,lo8(15)
/* #APP */

	mov r18,r25
	lsr r18
	lsr r18
	adc r25,r18

/* #NOAPP */
	subi r25,lo8(-(20))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+330,r25
	andi r28,lo8(16)
	subi r28,lo8(-(-8))
	sts _ZN17Lpx4TinyRomPlayer7decoderE+333,r28
	andi r24,lo8(16)
	rjmp .L118
.L75:
	rcall _ZN14Lpx4HybridCore7readOneEv.constprop.5
	tst r24
	breq .L119
	ldi r24,lo8(6)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r28,r24
	ldi r24,lo8(4)
	rcall _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	cpi r28,lo8(40)
	brlo .+2
	rjmp .L54
	ldi r25,lo8(8)
	eor r24,r25
	subi r24,lo8(-(-8))
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+329
	cp r25,r28
	breq .L93
	cp r28,r25
	brsh .L79
	sts _ZN17Lpx4TinyRomPlayer7decoderE+329,r28
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+333
	sts _ZN17Lpx4TinyRomPlayer7decoderE+333,r24
	mov r24,r18
	mov r28,r25
.L79:
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+330
	cp r28,r25
	breq .L94
	cp r28,r25
	brsh .L80
	sts _ZN17Lpx4TinyRomPlayer7decoderE+330,r28
	lds r18,_ZN17Lpx4TinyRomPlayer7decoderE+334
	sts _ZN17Lpx4TinyRomPlayer7decoderE+334,r24
	mov r24,r18
	mov r28,r25
.L80:
	sts _ZN17Lpx4TinyRomPlayer7decoderE+335,r24
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+330
	com r24
	add r28,r24
	sts _ZN17Lpx4TinyRomPlayer7decoderE+331,r28
	ldi r30,lo8(3)
.L76:
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+330
	subi r24,lo8(-(-1))
	lds r25,_ZN17Lpx4TinyRomPlayer7decoderE+329
	sub r24,r25
	sts _ZN17Lpx4TinyRomPlayer7decoderE+330,r24
	ldi r31,0
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+329))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+329))
	ldi r24,lo8(127)
	st Z,r24
	rjmp .L117
.L93:
	ldi r31,0
	ldi r30,0
.L78:
	subi r30,lo8(-(_ZN17Lpx4TinyRomPlayer7decoderE+333))
	sbci r31,hi8(-(_ZN17Lpx4TinyRomPlayer7decoderE+333))
	ld r25,Z
	add r24,r25
	st Z,r24
	rjmp .L119
.L94:
	ldi r30,lo8(1)
	ldi r31,0
	rjmp .L78
.L67:
	tst r15
	breq .L82
.L84:
	ldi r24,lo8(1)
.L41:
/* epilogue start */
	in r28,__SP_L__
	in r29,__SP_H__
	ldi r30, lo8(12)
	rjmp __epilogue_restores__ + ((18 - 12) * 2)
.L82:
	sbrc r18,1
	rjmp .L83
	movw r22,r28
	ldi r24,lo8(16)
	rcall _ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.10
	lds r24,_ZN17Lpx4TinyRomPlayer7decoderE+29
	ori r24,lo8(1<<1)
	sts _ZN17Lpx4TinyRomPlayer7decoderE+29,r24
.L83:
	ldi r30,lo8(_ZN17Lpx4TinyRomPlayer7decoderE+31)
	ldi r31,hi8(_ZN17Lpx4TinyRomPlayer7decoderE+31)
	movw r24,r28
	adiw r24,20
.L85:
	ld r18,Y+
	ld r19,Y+
	st Z+,r18
	st Z+,r19
	cp r24,r28
	cpc r25,r29
	brne .L85
	rjmp .L84
	.size	_ZN14Lpx4HybridCore15prepareSubframeEv.constprop.1, .-_ZN14Lpx4HybridCore15prepareSubframeEv.constprop.1
