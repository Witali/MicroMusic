#!/usr/bin/env python3
from __future__ import annotations
import sys, random
from pathlib import Path
from intel8080_tools import AsmPlus, crc_raw, crc32c, ihex
D=Path(__file__).resolve().parent
POLY=0x82F63B78

def bitround(k=0):
    return f'''        MOV A,B
        RAR
        MOV B,A
        MOV A,C
        RAR
        MOV C,A
        MOV A,D
        RAR
        MOV D,A
        MOV A,E
        RAR
        MOV E,A
        JNC NOXOR{k}
        XRI 078H      ; A already contains the shifted E
        MOV E,A
        MOV A,D
        XRI 03BH
        MOV D,A
        MOV A,C
        XRI 0F6H
        MOV C,A
        MOV A,B
        XRI 082H
        MOV B,A
NOXOR{k}:
'''

def source(size=32768, unroll=1, endmode='halt', comment=True):
    assert size in (24*1024,32*1024)
    assert unroll in (1,2,4,8)
    header='''; TABLELESS STANDARD CRC-32C (Castagnoli reflected 82F63B78h)
; Intel 8080 only, no RAM and no writes; SP reads ROM via POP H.
; Entire ROM [0000h,END) incl four-byte raw-CRC trailer has residue 0.
; Init=FFFFFFFF, xorout=FFFFFFFF for CRC-32C (test: 123456789 -> E3069283).
; BEWARE: EI+HLT success indication relies on INTE high after EI;
;          keep INTR inactive. A corrupt program may fail to execute.
        ORG 0000H
        DI
        LXI SP,0000H
        LXI B,0FFFFH
        LXI D,0FFFFH
NEXT4:  POP H             ; Caution: POP reads 2 bytes of ROM using SP
        MOV A,E
        XRA L
        MOV E,A
        MOV A,D
        XRA H
        MOV D,A
        POP H
        MOV A,C
        XRA L
        MOV C,A
        MOV A,B
        XRA H             ; XRA clears CY, also for first RAR
        MOV B,A
'''
    # Loop variable L counts down to zero; H serves as constant for DAD SP address check
    bias=(0x10000-size)&0xFFFF
    assert bias&0xFF==0
    header += f'        LXI H,{(bias+(32//unroll)):04X}H    ; H=bias high byte, L=iteration count\nBITLOOP:\n'
    bits=''.join(bitround(k) for k in range(unroll))
    tail='''        DCR L             ; does not alter CY
        JNZ BITLOOP
        DAD SP            ; carry iff SP >= ROM end address
        JNC NEXT4
        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
'''
    if endmode=='halt':
        tail+='''        EI                ; success INTE high
FAIL:   HLT               ; stop; fail leaves INTE low
'''
    elif endmode=='spin':
        tail+='''PASS:   EI
        JMP PASS
FAIL:   HLT
'''
    else: raise ValueError(endmode)
    tail+=f'        ORG {(size-4):04X}H\nFIXUP:  DB 0FFH,0FFH,0FFH,0FFH\n        END\n'
    return header+bits+tail

def patch(data):
    return bytes(data[:-4])+crc_raw(data[:-4]).to_bytes(4,'little')

def create(size=32768,unroll=1,endmode='halt'):
    name=f'crc32c_8080_{size//1024}k_u{unroll}_{endmode}'
    s=source(size,unroll,endmode)
    a=AsmPlus()
    img,used,lab=a.assemble(s,size)
    img=patch(img)
    assert crc_raw(img)==0, (name,hex(crc_raw(img)))
    (D/(name+'.asm')).write_text(s,encoding='utf-8')
    (D/(name+'.bin')).write_bytes(img)
    (D/(name+'.hex')).write_text(ihex(img),encoding='utf-8')
    first=lab['FIXUP']
    assert max(k for k in used if k<first)<512
    assert all(k < 512 or k >= size-4 for k in used)
    return name,img,lab,(max(k for k in used if k < first)+1)

if __name__=='__main__':
    print('CRC32C 123456789:',hex(crc32c(b'123456789')))
    for s in (24576,32768):
        for u in (1,2,4,8):
            for e in ('halt','spin'):
                n,_,lab,sz=create(s,u,e)
                print(n,sz,'bytes',lab.get('PASS'),lab['FAIL'])
