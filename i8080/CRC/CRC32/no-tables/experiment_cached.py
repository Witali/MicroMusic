from pathlib import Path
from generate import source, patch
from intel8080_tools import AsmPlus, ihex
D=Path(__file__).resolve().parent
for size in (24576,32768):
    s=source(size,1,'halt')
    s=s.replace('''BITLOOP:
        MOV A,B
        RAR''','''BITLOOP:
        RAR''')
    s=s.replace('''NOXOR0:
        DCR L             ; does not alter CY
        JNZ BITLOOP
        DAD SP''','''        DCR L
        JNZ BITLOOP
        JMP FINISH
NOXOR0: MOV A,B
        DCR L
        JNZ BITLOOP
FINISH: DAD SP''')
    s=s.replace(''';          keep INTR inactive. A corrupt program may fail to execute.''',''';          keep INTR inactive. A corrupt program may fail to execute.
; A is always equal to B at BITLOOP entry; avoid MOV A,B on feedback=1.''')
    a=AsmPlus(); img,used,lab=a.assemble(s,size);img=patch(img)
    name=f'crc32c_8080_{size//1024}k_cachedB'
    (D/f'{name}.asm').write_text(s)
    (D/f'{name}.bin').write_bytes(img)
    (D/f'{name}.hex').write_text(ihex(img))
    print(name,'bytes',lab['FAIL']+1, 'first skipped code at',lab['BITLOOP'])
