from pathlib import Path
P=Path('/mnt/data/crc32_work')

PROLOG = '''; Intel 8080, 64-KiB ROM self-test: CRC-32/MPEG-2 (MSB-first)
; polynomial 0x04C11DB7, init 0xFFFFFFFF, xorout 0, non-reflected.
; ROM[FFFC..FFFF] = CRC32 of ROM[0000..FFFB], most significant byte first.
; Successful validation: CRC32(ROM[0000..FFFF]) == 0.
; B:C:D:E = CRC32 MSB first, H:L = two ROM bytes read by POP H.
; SP points to ROM, and POP reads (does NOT write) ROM. Interrupts OFF.
; No RAM, no lookup table, no subroutines and no stack writes.
; All 65536 bytes checked. Requires real 64KiB mapped ROM.
        ORG 0000H
        DI
        LXI SP,0000H
        XRA A
        CMA
        MOV B,A
        MOV C,A
        MOV D,A
        MOV E,A
NEXT:   POP H             ; L = ROM[SP], H = ROM[SP+1]; SP+=2
        MOV A,L
        XRA B             ; CRC ^= first byte << 24
        MOV B,A
        MVI L,8           ; 8 bits of first byte
'''

def step(label, skip,poly):
    x=f'''{label}:    XCHG              ; swap CRC_low (DE) with temporary HL
        DAD H             ; CRC_low <<= 1, CY = carry to high half
        XCHG              ; restore temp HL; now DE = shifted CRC_low
        MOV A,C
        RAL               ; CRC_high <<= 1, including carry from low
        MOV C,A
        MOV A,B
        RAL
        MOV B,A           ; CY = former CRC bit31
        JNC {skip}        ; if old msb=1: CRC ^= polynomial
'''
    for reg,shift in (('B',24),('C',16),('D',8),('E',0)):
        x+=f'''        MOV A,{reg}
        XRI {(poly>>shift)&255:02X}H
        MOV {reg},A
'''
    x+=f'''{skip}:  DCR L
        JNZ {label}
'''
    return x

END='''        ; Both input bytes processed. Test if POP advanced SP to 0000H.
        LXI H,0000H
        DAD SP            ; HL = SP, no memory accessed
        MOV A,H
        ORA L
        JNZ NEXT
        ; Full 64-KiB CRC is zero if ROM matches its footer.
        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
        EI                ; result signal on INTE (hardware-dependent)
FAIL:   HLT               ; failure: interrupts disabled, success: enabled
'''

for name,poly in [('crc32_mpeg2_8080',0x04C11DB7),('crc32c_msb_8080',0x1EDC6F41)]:
  lines=PROLOG.replace('CRC-32/MPEG-2','CRC-32/MPEG-2' if name.startswith('crc32_mpeg') else 'CRC-32C non-reflected').replace('0x04C11DB7', f'0x{poly:08X}')
  lines+=step('BIT0','NOXOR0',poly)
  lines+='''        MOV A,H           ; second byte saved in H from POP
        XRA B
        MOV B,A
        MVI L,8
'''
  lines+=step('BIT1','NOXOR1',poly)
  lines+=END
  (P/(name+'.asm')).write_text(lines)
  print(name,len(lines),'chars')
