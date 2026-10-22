#!/usr/bin/env python3
"""Rebuild and independently verify Intel 8080 dual-CRC16 ROM images."""
from pathlib import Path
import csv
from assembler_8080 import assemble
from build_rom import patch,crc16,crc32,intel_hex,POLYS
ROOT=Path(__file__).resolve().parent.parent
PROFILES={
  'bitwise_shared':(44,50200728),
  'bitwise_shared_parity':(42,50200714),
  'bitwise_shared_parity_reset':(41,50200710),
  'bitwise_shared_parity_u2':(47,42336394),
  'bitwise_shared_parity_u4':(57,38404234),
}
LEGACY={'fast75_peephole':75,'fast_p47_rotate':82}

def main():
    for name,(size,cycles) in PROFILES.items():
        source=(ROOT/'asm'/f'{name}.asm').read_text()
        compiled,_=assemble(source)
        assert len(compiled)==size,(name,len(compiled),size)
        assert compiled==(ROOT/'bin'/f'{name}.bin').read_bytes(),f'{name}: ASM/BIN mismatch'
        rom=patch(compiled)
        assert len(rom)==65536 and all(crc16(rom,p)==0 for p in POLYS)
        assert crc32(rom)==0
        (ROOT/'rom'/f'{name}_64K.bin').write_bytes(rom)
        (ROOT/'hex'/f'{name}_64K.hex').write_text(intel_hex(rom))
        print(f'{name:30s} {size:2d} bytes | {cycles/65536:.5f} T/ROM byte | footer={rom[-4:].hex()}')
    for name,size in LEGACY.items():
        assembled,_=assemble((ROOT/'previous_versions'/f'{name}.asm').read_text())
        assert len(assembled)==size
        assert assembled==(ROOT/'previous_versions'/f'{name}.bin').read_bytes()
    print('PASS: all ASM==BIN; all ROM CRC25==CRC47==CRC32==0; HEX generated')
if __name__=='__main__':main()
