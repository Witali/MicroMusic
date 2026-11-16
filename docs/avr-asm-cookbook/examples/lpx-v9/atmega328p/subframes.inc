/* Parse frames and pulse packets and select LPC anchors. */
.L249:
	cpse r24,__zero_reg__
	rjmp .L86
	lds r24,_ZL7decoder+19
	mov r25,r24
	andi r25,lo8(7)
	brne .+2
	rjmp .L87
.L112:
	lds r24,_ZL7decoder+19
	ldi r25,0
	lds r18,_ZL7decoder+26
	mov r26,r18
	andi r26,lo8(8)
	mov r6,r26
	ldi r20,lo8(3)
	ldi r21,0
	sbrc r18,3
	rjmp .L88
	ldi r20,lo8(1)
	ldi r21,0
.L88:
	and r24,r20
	and r25,r21
	or r24,r25
	brne .+2
	rjmp .L113
.L139:
	lds r25,_ZL7decoder+19
	mov r19,r25
	andi r19,lo8(7)
	mov r7,r19
	lds r24,_ZL7decoder+31
	mov r26,r24
	ldi r27,0
	lsl r26
	rol r27
	subi r26,lo8(-(_ZL7decoder+356))
	sbci r27,hi8(-(_ZL7decoder+356))
	std Y+6,r27
	std Y+5,r26
	lds r18,_ZL7decoder+30
	sbrc r18,2
	rjmp .L114
	ldi r19,lo8(10)
	eor r24,r19
	mov r16,r24
	ldi r17,0
	lsl r16
	rol r17
	subi r16,lo8(-(_ZL7decoder+356))
	sbci r17,hi8(-(_ZL7decoder+356))
	andi r25,lo8(3)
	brne .L142
	cpse r7,__zero_reg__
	rjmp .L143
	sbrc r18,1
	rjmp .L143
	movw r22,r16
	ldi r24,0
	call _ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8
.L144:
	mov r24,r7
	lsr r24
	lsr r24
	subi r24,lo8(-(1))
	ldd r22,Y+5
	ldd r23,Y+6
	lsl r24
	lsl r24
	lsl r24
	call _ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8
	lds r24,_ZL7decoder+30
	ori r24,lo8(1<<1)
	sts _ZL7decoder+30,r24
.L142:
	lsl r7
	ldi r24,lo8(1)
	add r24,r7
	andi r24,lo8(7)
	std Y+1,r24
	std Y+8,r17
	std Y+7,r16
	ldi r26,lo8(_ZL7decoder+32)
	ldi r27,hi8(_ZL7decoder+32)
	ldd r20,Y+5
	ldd r21,Y+6
	subi r20,-20
	sbci r21,-1
.L145:
	ldd r30,Y+5
	ldd r31,Y+6
	ld r18,Z+
	ld r19,Z+
	std Y+6,r31
	std Y+5,r30
	ldd r30,Y+7
	ldd r31,Y+8
	ld r24,Z+
	ld r25,Z+
	std Y+8,r31
	std Y+7,r30
	ldd r31,Y+1
/* #APP */

	clr r17
	movw r22,r18
	sub r22,r24
	sbc r23,r25
	brge 1f
	dec r17
	1:
	mul r22,r31
	movw r4,r0
	clr r6
	mul r23,r31
	add r5,r0
	adc r6,r1
	sbrc r17,7
	sub r6,r31
	clr __zero_reg__
	andi r17,7
	add r4,r17
	adc r5,__zero_reg__
	adc r6,__zero_reg__
	.rept 3
	asr r6
	ror r5
	ror r4
	.endr
	add r4,r24
	adc r5,r25

/* #NOAPP */
	st X+,r4
	st X+,r5
	ldd r18,Y+5
	ldd r19,Y+6
	cp r20,r18
	cpc r21,r19
	breq .+2
	rjmp .L145
	rjmp .L86
.L87:
	lds r25,_ZL7decoder+30
	ori r25,lo8(1<<2)
	sts _ZL7decoder+30,r25
	sbrc r24,3
	rjmp .L89
	ldi r16,lo8(_ZL7decoder+336)
	ldi r17,hi8(_ZL7decoder+336)
	movw r30,r16
.L90:
	ldd r24,Z+10
	st Z+,r24
	ldi r27,hi8(_ZL7decoder+346)
	cpi r30,lo8(_ZL7decoder+346)
	cpc r31,r27
	brne .L90
	lds r24,_ZL7decoder+26
	sbrs r24,1
	rjmp .L177
	ldi r30,lo8(6)
	std Y+1,r30
.L91:
	call _ZN14Lpx4HybridCore7readOneEv.constprop.5
	cpse r24,__zero_reg__
	rjmp .L92
	lds r24,_ZL7decoder+30
	sbrs r24,0
	rjmp .L84
.L89:
	lds r24,_ZL7decoder+30
	sbrc r24,0
	rjmp .L105
	ldi r30,lo8(_ZL7decoder+336)
	ldi r31,hi8(_ZL7decoder+336)
.L106:
	ldd r24,Z+10
	st Z+,r24
	cp r12,r30
	cpc r13,r31
	brne .L106
.L105:
	lds r24,_ZL7decoder+30
	ori r24,lo8(1<<0)
	sts _ZL7decoder+30,r24
	lds r24,_ZL7decoder+19
	ldi r25,lo8(8)
	eor r25,r24
	sts _ZL7decoder+19,r25
	com r24
	andi r24,lo8(8)
	lds r25,_ZL7decoder+26
	sbrs r25,3
	rjmp .L107
	cpse r24,__zero_reg__
	rjmp .L107
.L256:
	lds r24,_ZL7decoder+29
	tst r24
	brne .+2
	rjmp .L112
	rjmp .L258
.L177:
	ldi r31,lo8(5)
	std Y+1,r31
	rjmp .L91
.L92:
	call _ZN14Lpx4HybridCore7readOneEv.constprop.5
	mov r5,r24
	ldi r24,lo8(1)
	cpse r5,__zero_reg__
	rjmp .L248
	ldi r24,0
.L94:
	ldd r25,Y+1
	subi r25,lo8(-(-4))
	mov r7,r25
	sub r7,r24
	lds r4,_ZL7decoder+26
	mov r18,r4
	andi r18,lo8(2)
	mov r4,r18
	inc r4
	inc r4
	swap r4
	ldi r27,lo8(-16)
	and r4,r27
	clr r6
	dec r6
	ldd r19,Y+1
	add r19,r24
	std Y+1,r19
.L104:
	std Y+4,__zero_reg__
.L97:
	call _ZN14Lpx4HybridCore7readOneEv.constprop.5
	cpse r24,__zero_reg__
	rjmp .L95
	lds r25,_ZL7decoder+29
	cpse r25,__zero_reg__
	rjmp .L96
	ldd r20,Y+4
	subi r20,lo8(-(1))
	std Y+4,r20
	cpi r20,lo8(8)
	brne .L97
	ldd r24,Y+1
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	rjmp .L96
.L248:
	lds r25,_ZL7decoder+30
	sbrc r25,0
	rjmp .L94
	rjmp .L84
.L99:
	asr r19
	ror r18
	rjmp .L100
.L107:
	ldi r24,lo8(5)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	std Y+1,r24
	ldi r24,lo8(3)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	lsl r24
	sts _ZL7decoder+24,r24
	tst r24
	breq .L178
	ldi r24,lo8(7)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	subi r24,lo8(-(18))
.L110:
	sts _ZL7decoder+23,r24
	ldd r18,Y+1
	mov r30,r18
	ldi r31,0
	lsl r30
	rol r31
	subi r30,lo8(-(_ZL11scaleValues))
	sbci r31,hi8(-(_ZL11scaleValues))
/* #APP */

	lpm r24, Z+
	lpm r25, Z

/* #NOAPP */
	ldi r30,4
	1:
	lsl r24
	rol r25
	dec r30
	brne 1b
	sts _ZL7decoder+14+1,r25
	sts _ZL7decoder+14,r24
	rjmp .L256
.L178:
	ldi r24,lo8(18)
	rjmp .L110
.L113:
	tst r6
	breq .L116
	ldi r24,lo8(7)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r25,r24
	andi r25,lo8(63)
	mov r18,r25
	ldi r19,0
	subi r18,-2
	sbci r19,-1
	asr r19
	ror r18
	asr r19
	ror r18
	add r18,r25
	sts _ZL7decoder+330,r18
	sbrs r24,6
	rjmp .L179
	ldi r24,lo8(7)
.L117:
	sts _ZL7decoder+333,r24
	sts _ZL7decoder+28,__zero_reg__
	ldi r27,lo8(1)
	sts _ZL7decoder+27,r27
.L136:
	lds r24,_ZL7decoder+29
	tst r24
	brne .+2
	rjmp .L139
	rjmp .L258
.L179:
	ldi r24,lo8(-8)
	rjmp .L117
.L116:
	sts _ZL7decoder+28,__zero_reg__
	ldi r24,lo8(2)
	sts _ZL7decoder+27,r24
	sbrs r18,1
	rjmp .L180
	ldi r24,lo8(4)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	std Y+1,r24
	ldi r24,lo8(5)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	cpi r24,lo8(25)
	brlo .+2
	rjmp .L84
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZL9pulseHigh))
	sbci r31,hi8(-(_ZL9pulseHigh))
/* #APP */

	lpm r30, Z

/* #NOAPP */
	ldd r24,Y+1
	andi r24,lo8(3)
	mov r31,r30
	andi r31,lo8(28)
	mov r5,r31
	or r5,r24
	mov r24,r5
	lsr r30
	lsr r30
	lsr r30
	andi r30,lo8(28)
	ldd r7,Y+1
	lsr r7
	lsr r7
	or r7,r30
.L120:
	ldi r18,lo8(_ZL7decoder+330)
	ldi r19,hi8(_ZL7decoder+330)
	std Y+6,r19
	std Y+5,r18
	ldi r17,0
	mov r5,r24
.L126:
	lds r24,_ZL7decoder+26
	sbrc r24,1
	rjmp .L121
	ldi r24,lo8(5)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	mov r16,r24
	andi r16,lo8(15)
	mov r18,r16
	ldi r19,0
	subi r18,-2
	sbci r19,-1
	asr r19
	ror r18
	asr r19
	ror r18
	add r16,r18
	sbrs r24,4
	rjmp .L181
	ldi r24,lo8(8)
.L122:
	add r16,r6
	ldd r26,Y+5
	ldd r27,Y+6
	st X+,r16
	std Y+6,r27
	std Y+5,r26
	adiw r26,2
	st X,r24
	ldi r27,lo8(20)
	add r6,r27
	cpi r17,lo8(1)
	breq .+2
	rjmp .L183
	lds r24,_ZL7decoder+26
	sbrs r24,7
	rjmp .L128
	call _ZN14Lpx4HybridCore7readOneEv.constprop.5
	tst r24
	breq .L128
	ldi r24,lo8(6)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	std Y+1,r24
	ldi r24,lo8(4)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	cpi r24,lo8(8)
	brlo .L131
	subi r24,lo8(-(-16))
.L131:
	ldd r30,Y+1
	cpi r30,lo8(40)
	brlo .+2
	rjmp .L84
	lds r25,_ZL7decoder+330
	cp r25,r30
	brsh .L184
	lds r18,_ZL7decoder+331
	cp r18,r30
	brlo .L185
.L132:
	mov r30,r17
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder))
	sbci r31,hi8(-(_ZL7decoder))
	movw r26,r30
	subi r26,-74
	sbci r27,-2
	ld r18,X
	ldd r19,Y+1
	cpse r19,r18
	rjmp .L252
	subi r30,-77
	sbci r31,-2
	ld r25,Z
	add r24,r25
	st Z,r24
.L128:
	lds r24,_ZL7decoder+27
	subi r24,lo8(-(-1))
	mov r30,r24
	ldi r31,0
	subi r30,lo8(-(_ZL7decoder+330))
	sbci r31,hi8(-(_ZL7decoder+330))
.L137:
	tst r24
	brne .+2
	rjmp .L136
	ld r25,Z
	subi r25,lo8(-(-1))
	ld r18,-Z
	sub r25,r18
	std Z+1,r25
	subi r24,lo8(-(-1))
	rjmp .L137
.L180:
	mov r7,__zero_reg__
	ldi r24,0
	rjmp .L120
.L183:
	ldi r17,lo8(1)
	rjmp .L126
.L121:
	mov r16,r5
	cpse r17,__zero_reg__
	mov r16,r7
.L123:
	ldi r24,lo8(4)
	call _ZN14Lpx4HybridCore8readBitsEh.constprop.6
	cpi r24,lo8(8)
	brlo .L125
	subi r24,lo8(-(-16))
.L125:
	cpi r16,lo8(20)
	brsh .+2
	rjmp .L122
	rjmp .L84
.L181:
	ldi r24,lo8(-8)
	rjmp .L122
.L184:
	ldi r17,0
	rjmp .L132
.L185:
	ldi r17,lo8(2)
	rjmp .L133
.L114:
	sbrc r18,1
	rjmp .L140
	ldd r22,Y+5
	ldd r23,Y+6
	ldi r24,0
	call _ZN14Lpx4HybridCore12convertLsfAtEhPi.constprop.8
	lds r24,_ZL7decoder+30
	ori r24,lo8(1<<1)
	sts _ZL7decoder+30,r24
.L140:
	cpse r7,__zero_reg__
	rjmp .L86
	ldi r30,lo8(_ZL7decoder+32)
	ldi r31,hi8(_ZL7decoder+32)
	ldd r24,Y+5
	ldd r25,Y+6
	adiw r24,20
.L141:
	ldd r26,Y+5
	ldd r27,Y+6
	ld r18,X+
	ld r19,X+
	std Y+6,r27
	std Y+5,r26
	st Z+,r18
	st Z+,r19
	cp r24,r26
	cpc r25,r27
	brne .L141
