#!/usr/bin/env python3
"""Machine-instruction-level golden test for optimized 8080 CRC-32C bit core."""
from generate import bitround
from intel8080_tools import AsmPlus, Emulator, crc32c

fold4='''        POP H
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
        XRA H
        MOV B,A
'''
source='''        ORG 0000H
        DI
        LXI SP,0800H
        LXI B,0FFFFH
        LXI D,0FFFFH
'''
for i in range(2):
    source+=fold4+f'        MVI L,020H\nLOOP{i}:\n'+bitround(i)
    source+=f'        DCR L\n        JNZ LOOP{i}\n'
source+='''        POP H
        MOV A,E
        XRA L
        MOV E,A
        MVI L,08H
LOOP2:
'''+bitround(2)+'''        DCR L
        JNZ LOOP2
STOP:   HLT
        ORG 0800H
        DB 031H,032H,033H,034H,035H,036H,037H,038H,039H,000H
        END
'''
a=AsmPlus()
rom,_,labels=a.assemble(source,0x1000)
e=Emulator(rom)
e.run_to(labels['STOP'],max_steps=100000)
assert e.sp==0x080A
val=(e.state_crc()^0xFFFFFFFF)
assert val==crc32c(b'123456789')==0xE3069283
print(f'8080 CPU golden CRC-32C("123456789") = {val:08X}: PASS')
