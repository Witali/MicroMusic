#!/usr/bin/env python3
"""Build small PIC16F1503 real-instruction Timer2/PWM3 diagnostic HEX.
Not the musical firmware. PIC encoding per DS40001607D Table 27-3.
The program increments PWM3DCH in each Timer2/4 interrupt.
"""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
ops=[]; labels={}

def emit(kind,*args): ops.append((kind,args))
def label(name): labels[name]=len(ops)
def movlw(x):emit('movlw',x)
def movlb(x):emit('movlb',x)
def movwf(f):emit('movwf',f)
def bcf(f,b):emit('bcf',f,b)
def bsf(f,b):emit('bsf',f,b)
def incf(f):emit('incf',f)
def addwf(f):emit('addwf',f)
def andwf(f):emit('andwf',f)
def btfsc(f,b):emit('btfsc',f,b)
def goto(l):emit('goto',l)
def bra(l):emit('bra',l)

goto('reset')
while len(ops)<4:emit('nop')
goto('handler')
label('handler')
bcf(0x11,1)             # PIR1.TMR2IF cleared before next timer interrupt
movlb(12);movlw(64);addwf(0x17)   # low two duty bits in PWM3DCL<7:6>
btfsc(0x03,0);incf(0x18)          # carry propagates to high PWM3DCH
movlw(63);andwf(0x18)             # wrap high duty after 64 * 4=256 levels
emit('retfie')
label('reset')
movlb(1);movlw(0x7a);movwf(0x19) # OSCCON 16MHz INTOSC
movlb(3);bcf(0x0c,2)             # ANSELA digital RA2
movlb(1);bcf(0x0c,2)             # TRISA RA2 output
movlb(0);movlw(63);movwf(0x1b)   # PR2 63 -> 62.5k PWM
movlw(0);movwf(0x1a)             # TMR2
movlw(0x1c);movwf(0x1c)          # Timer2 ON, interrupt postscale 1:4
movlb(12);movlw(32);movwf(0x18) # 50%: duty=128 of 256 ticks
movlw(0);movwf(0x17)              # PWM3DCL<7:6> = 0
movlw(0xc0);movwf(0x19)          # PWM3EN/PWM3OE
movlb(1);bsf(0x11,1)              # PIE1.TMR2IE
movlb(0);bsf(0x0b,6);bsf(0x0b,7) # PEIE and GIE
label('idle');bra('idle')
word=[]
for i,(op,a) in enumerate(ops):
    if op=='goto': w=0x2800|labels[a[0]]
    elif op=='bra':
        delta=labels[a[0]]-i-1
        assert -256<=delta<=255
        w=0x3200|(delta&511)
    elif op=='movlw':w=0x3000|a[0]
    elif op=='movlb':w=0x0020|a[0]
    elif op=='movwf':w=0x0080|a[0]
    elif op=='bcf':w=0x1000|(a[1]<<7)|a[0]
    elif op=='bsf':w=0x1400|(a[1]<<7)|a[0]
    elif op=='incf':w=0x0a80|a[0]
    elif op=='addwf':w=0x0780|a[0]
    elif op=='andwf':w=0x0580|a[0]
    elif op=='btfsc':w=0x1800|(a[1]<<7)|a[0]
    elif op=='retfie':w=0x0009
    elif op=='nop':w=0
    else:raise RuntimeError(op)
    word.append(w)

def record(addr,type,data):
    buf=[len(data),addr>>8,addr&255,type,*data]
    return ':'+''.join('%02X'%(v&255) for v in buf+[(-sum(buf))&255])
b=[]
for w in word:b.extend([w&255,w>>8])
hexstr='\n'.join(record(i,0,b[i:i+16]) for i in range(0,len(b),16))+'\n'+record(0,1,[])+'\n'
p=(R/'firmware'/'diagnostic_pwm_irq.hex');p.write_text(hexstr)
s='''; PIC16F1503 Timer2/PWM3 instruction-level diagnostics only. NOT a musical firmware.
; Machine words below use documented enhanced PIC16F1 opcodes.
; Compile with tools/build_diagnostic.py (no XC8 needed for diagnostics).
; PWM3 is on RA2, 14-pin DIP pin 11.
'''
for i,(op,args) in enumerate(ops):
    for k,v in labels.items():
        if v==i:s+=k+':\n'
    s+=f'    {op.upper():7} '+', '.join(f'0x{x:02x}' if isinstance(x,int) else x for x in args)+f'   ; 0x{i:04X}: 0x{word[i]:04X}\n'
(R/'firmware'/'diagnostic_pwm_irq.asm').write_text(s)
print('Diagnostic',len(word),'words, handler',labels['handler'],'reset',labels['reset'])
