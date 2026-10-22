#!/usr/bin/env python3
"""Build and verify ROM-only Intel 8080 full EPROM CRC-32C verifier.

The compiled ROM contains TWO stages:
(1) exact validation of its own 1 KiB CRC lookup table, without using it,
(2) standard reflected CRC-32C over the entire ROM including all code,
    the already-validated table and a four-byte residue trailer.

All code uses actual Intel 8080 instructions (no RAM, no calls/returns).
Run: python3 build.py
"""
from __future__ import annotations
from pathlib import Path
import random
from intel8080_tools import AssemblerExtended, EmulatorExtended, crc_raw, crc32c, ihex, table_crc32c

ROOT = Path(__file__).resolve().parent
POLY = 0x82F63B78
SIZES = (0x6000,0x8000)

HEADER = '''; INTEL 8080, ROM-only CRC-32C self-test, exact 1-KiB table precheck.
; No RAM, no CALL/RET/PUSH, SP reads ROM only through POP H.
; 0000h: startup -> 0500h table self-test, independent of table values
; 0100h-04FFh: 4 x 256 byte-planes of standard CRC-32C lookup table
; 0500h: verifier (checks ALL 1024 table bytes mathematically)
; Entire [0000h,ENDROM) is checked after table passes verification.
; Last four bytes store pre-xor raw CRC32C of [0000h,ENDROM-4)
; in little-endian order, yielding RAW CRC32C(full ROM)=00000000h.
; A=not a result; CPU halts with INTE=1 pass, INTE=0 fail.
; NOTE: keep INTR low; EI+HLT with active interrupts is unsafe without RAM.
        ORG 0000H
RESET:  DI
        JMP VERIFY_TABLE

CRC_START:
        LXI SP,0000H      ; SP is read-only ROM address pointer
        LXI B,0FFFFH      ; CRC highest 16 bits: B:C
        LXI D,0FFFFH      ; CRC lowest 16 bits: D:E
NEXT4:  POP H            ; 2 ROM bytes (L,H), SP += 2
        MOV A,E
        XRA L
        MOV E,A
        MOV A,D
        XRA H
        MOV D,A
        POP H            ; 2 more ROM bytes
        MOV A,C
        XRA L
        MOV C,A
        MOV A,B
        XRA H
        MOV B,A

; Four table rounds per four source bytes, each time CRC=(CRC>>8)^T[E].
'''

TABLEROUND = '''        MOV L,E           ; index = CRC low byte
        MVI H,01H         ; byte plane #0
        MOV A,D
        XRA M
        MOV E,A
        INR H             ; byte plane #1
        MOV A,C
        XRA M
        MOV D,A
        INR H             ; byte plane #2
        MOV A,B
        XRA M
        MOV C,A
        INR H             ; byte plane #3
        MOV B,M
'''

TAIL = '''        LXI H,0000H      ; HL := SP
        DAD SP
        MOV A,H
        CPI {endhi:02X}H         ; address end after all 4-byte blocks
        JNZ NEXT4
        MOV A,B           ; raw residue must equal zero
        ORA C
        ORA D
        ORA E
        JNZ STOP
        EI                ; success: assert INTE, do not take interrupts
STOP:   HLT               ; fail: DI from RESET remains in effect
'''

# The table checker ASM is deliberately fixed, independent of data table.
VERIFY_SRC = (ROOT / 'verify_fragment.asm').read_text(encoding='utf-8')

def db_bytes(byteset):
    return '\n'.join('        DB '+','.join(f'{x:02X}H' for x in byteset[k:k+16]) for k in range(0,len(byteset),16))


def render_source(size):
    assert size in SIZES
    code = HEADER + '\n'.join(TABLEROUND for _ in range(4)) + TAIL.format(endhi=size>>8)
    table=table_crc32c()
    for p in range(4):
        code+=f'\n        ORG {p+1:02X}00H\n; CRC-32C table byte plane {p} of 4 (standard reflected poly 82F63B78h)\n'
        code+=db_bytes([(entry>>(8*p))&255 for entry in table])+'\n'
    code+='\n'+VERIFY_SRC+'\n'
    code+=f'\n        ORG {size-4:04X}H\nCRC_FIXUP: DB 0FFH,0FFH,0FFH,0FFH ; replaced by build.py\n'
    code+='        END\n'
    return code


def build(size, variant=''): 
    src=render_source(size)
    asm=AssemblerExtended()
    rom, used, labels=asm.assemble(src,size)
    assert labels['CRC_START']<0x100
    assert labels['STOP']<0x100
    assert labels['VERIFY_TABLE']==0x500
    assert labels['CRC_FIXUP']==size-4
    for p in range(4):
        assert all(i in used for i in range(0x100+p*0x100,0x200+p*0x100))
    raw=crc_raw(rom[:-4])
    rom[-4:]=raw.to_bytes(4, 'little')
    assert crc_raw(rom)==0
    stem=f'crc32c_8080_checked_{size//1024}k'
    (ROOT/(stem+'.asm')).write_text(src,encoding='utf-8')
    (ROOT/(stem+'.bin')).write_bytes(rom)
    (ROOT/(stem+'.hex')).write_text(ihex(rom),encoding='ascii')
    return bytes(rom),used,labels


def run(rom,labels):
    emu=EmulatorExtended(rom)
    # measure table validation from reset to first instruction of CRC stage
    emu.run_to({labels['CRC_START'],labels['STOP']},max_steps=1000000)
    valid_table=(emu.pc==labels['CRC_START'])
    table_cycles=emu.cycles
    if valid_table:
        emu.run_to({labels['STOP']},max_steps=3000000)
    emu.one()  # execute terminating HLT
    assert emu.halt
    return emu,valid_table,table_cycles


def tests():
    assert crc32c(b'123456789')==0xE3069283
    assert len(table_crc32c())==256
    assert table_crc32c()[1]==0xF26B8303
    assert all(
        ((table_crc32c()[2*i]>>1) ^ (POLY if table_crc32c()[2*i]&1 else 0)) == table_crc32c()[i]
        and table_crc32c()[2*i+1] == (table_crc32c()[2*i]^table_crc32c()[1])
        for i in range(1,128)
    )
    for size in SIZES:
        rom,used,labels=build(size)
        emu,table_ok,table_cycles=run(rom,labels)
        assert table_ok and emu.enabled and emu.sp==size
        print(f'{size//1024:2d} KiB  main={labels["CRC_START"]:04X} STOP={labels["STOP"]:04X} '
              f'verifier={labels["VERIFY_TABLE"]:04X}  tables={table_cycles:,} clocks ({table_cycles/3.5e6:.6f} sec)  '
              f'total={emu.cycles:,} clocks ({emu.cycles/3.5e6:.6f} sec), '
              f'patch={rom[-4:].hex().upper()}')
        # Every table plane + low/high pair, plus edge and boundaries.
        for addr in (0x100,0x101,0x102,0x17f,0x1fe,0x1ff,
                     0x200,0x201,0x2fe,0x2ff,
                     0x300,0x301,0x3fe,0x3ff,
                     0x400,0x401,0x4fe,0x4ff):
            bad=bytearray(rom)
            bad[addr]^=0x20
            e,tok,tc=run(bad,labels)
            assert not tok and not e.enabled and e.sp == 0, (hex(addr), e.sp)
            assert tc < table_cycles
        # If a table byte is deliberately modified and the final CRC
        # recalculated, table precheck MUST still reject the change.
        for addr in (0x100,0x179,0x201,0x2ff,0x350,0x4ff):
            bad=bytearray(rom)
            bad[addr]^=0x40
            bad[-4:]=crc_raw(bad[:-4]).to_bytes(4,'little')
            assert crc_raw(bad)==0
            e,tok,tc=run(bad,labels)
            assert not tok and not e.enabled
        for addr in (0x80,0x800,0x501, size//2, size-8, size-1):
            bad=bytearray(rom)
            bad[addr]^=1
            e,tok,tc=run(bad,labels)
            if addr == 0x501: # verifier code itself corrupted; cannot guarantee behavior
                continue
            assert tok and not e.enabled and e.sp==size, (addr, tok,e.enabled,e.sp)
        # Image with additional harmless extra ROM data and freshly patched CRC.
        rng=random.Random(4096+size)
        for rep in range(2):
            alt=bytearray(rom)
            for addr in range(0x900,size-4,997):
                alt[addr]=rng.randrange(256)
            alt[-4:]=crc_raw(alt[:-4]).to_bytes(4,'little')
            e,tok,tc=run(alt,labels)
            assert tok and e.enabled
    print('All instruction-level tests passed')

if __name__=='__main__': tests()
