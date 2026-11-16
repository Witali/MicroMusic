/* Read and validate the LPX v9 stream header in main. */
	.section	.text._ZN14Lpx4HybridCore5beginEPKhj.constprop.13,"ax",@progbits
	.type	_ZN14Lpx4HybridCore5beginEPKhj.constprop.13, @function
_ZN14Lpx4HybridCore5beginEPKhj.constprop.13:
/* prologue: function */
/* frame size = 0 */
/* stack size = 0 */
.L__stack_usage = 0
	ldi r24,lo8(_ZL5voice)
	ldi r25,hi8(_ZL5voice)
	sts _ZL7decoder+1,r25
	sts _ZL7decoder,r24
	ldi r24,lo8(lpx_audio_end-_ZL5voice)
	ldi r25,hi8(lpx_audio_end-_ZL5voice)
	sts _ZL7decoder+2+1,r25
	sts _ZL7decoder+2,r24
	lds r24,_ZL7decoder+4
	lds r25,_ZL7decoder+4+1
	sts _ZL7decoder+6+1,r25
	sts _ZL7decoder+6,r24
	call _ZN14Lpx4HybridCore10resetStateEv.constprop.14
	call _ZN14Lpx4HybridCore6read16Ev.constprop.15
	cpi r24,76
	sbci r25,57
	breq .L57
.L61:
	ldi r24,lo8(1)
.L68:
	sts _ZL7decoder+29,r24
	ldi r24,0
	ret
.L57:
	call _ZN14Lpx4HybridCore8readByteEv.constprop.16
	cpi r24,lo8(15)
	breq .L59
	mov r25,r24
	andi r25,lo8(125)
	cpi r25,lo8(4)
	breq .L59
	ldi r24,lo8(2)
	rjmp .L68
.L59:
	sts _ZL7decoder+26,r24
	call _ZN14Lpx4HybridCore6read16Ev.constprop.15
	sts _ZL7decoder+8+1,r25
	sts _ZL7decoder+8,r24
	call _ZN14Lpx4HybridCore6read16Ev.constprop.15
	sts _ZL7decoder+4+1,r25
	sts _ZL7decoder+4,r24
	call _ZN14Lpx4HybridCore6read16Ev.constprop.15
	sts _ZL7decoder+10+1,r25
	sts _ZL7decoder+10,r24
	call _ZN14Lpx4HybridCore6read16Ev.constprop.15
	sts _ZL7decoder+12+1,r25
	sts _ZL7decoder+12,r24
	lds r24,_ZL7decoder+4
	lds r25,_ZL7decoder+4+1
	sts _ZL7decoder+6+1,r25
	sts _ZL7decoder+6,r24
	cpi r24,20
	cpc r25,__zero_reg__
	brlo .L60
	ldi r24,lo8(20)
	ldi r25,0
.L60:
	sts _ZL7decoder+20,r24
	call _ZN14Lpx4HybridCore6read16Ev.constprop.15
	lds r18,_ZL7decoder+4
	lds r19,_ZL7decoder+4+1
	subi r18,1
	sbc r19,__zero_reg__
	cp r18,__zero_reg__
	sbci r19,-6
	brlo .+2
	rjmp .L61
	cpi r24,lo8(lpx_audio_end-_ZL5voice-13)
	sbci r25,hi8(lpx_audio_end-_ZL5voice-13)
	breq .+2
	rjmp .L61
	lds r24,_ZL7decoder+29
	cpse r24,__zero_reg__
	rjmp .L61
	lds r24,_ZL7decoder+8
	lds r25,_ZL7decoder+8+1
	cpi r24,64
	sbci r25,31
	breq .+2
	rjmp .L61
	lds r24,_ZL7decoder+10
	lds r25,_ZL7decoder+10+1
	cpi r24,1
	sbci r25,64
	brlo .+2
	rjmp .L61
	lds r24,_ZL7decoder+12
	lds r25,_ZL7decoder+12+1
	cpi r24,-50
	sbci r25,44
	brlo .+2
	rjmp .L61
	ldi r24,lo8(1)
/* epilogue start */
	ret
	.size	_ZN14Lpx4HybridCore5beginEPKhj.constprop.13, .-_ZN14Lpx4HybridCore5beginEPKhj.constprop.13
