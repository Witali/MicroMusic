from pathlib import Path
from build_crc32 import PROLOG, END, step
P=Path('/mnt/data/crc32_work')
# As in fast model, but one common 8-bit bit processing block, an extra check for half word.
for name,poly in [('crc32_mpeg2_8080_compact',0x04C11DB7),('crc32c_msb_8080_compact',0x1EDC6F41)]:
 s=PROLOG.replace('CRC-32/MPEG-2','CRC-32/MPEG-2' if name.startswith('crc32_mpeg') else 'CRC-32C polynomial / non-reflected').replace('0x04C11DB7',f'0x{poly:08X}').replace('MVI L,8           ; 8 bits of first byte','MVI L,16          ; process two bytes in a common bit loop')
 # Use block without bottom label
 block=step('BIT','NOXOR',poly)
 block=block.split('NOXOR:  DCR L')[0]
 s+=block
 s+='''NOXOR:  DCR L
        JZ ENDP
        MOV A,L
        CPI 8             ; 8 bits remain -> switch to second byte
        JNZ BIT
        MOV A,H           ; second byte from POP
        XRA B
        MOV B,A
        JMP BIT
ENDP:
'''
 s+=END
 (P/(name+'.asm')).write_text(s)
