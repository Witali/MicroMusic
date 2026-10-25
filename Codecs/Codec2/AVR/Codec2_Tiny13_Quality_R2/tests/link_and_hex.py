#!/usr/bin/env python3
"""Resolve AVR relocation records after LLVM assembly (not a generic linker).
Only support explicitly checked R_AVR_13_PCREL, R_AVR_LO8_LDI and R_AVR_HI8_LDI.
Always reject other/unknown records and out-of-range addresses.
"""
from pathlib import Path
import re,subprocess,hashlib
P=Path(__file__).resolve().parents[1]/'build'
obj=P/'demo.o'
raw=bytearray((P/'unlinked.bin').read_bytes())
symtab=subprocess.check_output(['readelf','-sW',str(obj)],text=True)
reloc=subprocess.check_output(['readelf','-rW',str(obj)],text=True)
sym={}
for row in symtab.splitlines():
 m=re.match(r'\s*(\d+):\s+([0-9a-fA-F]+)\s+\d+\s+\w+\s+\w+\s+\w+\s+(\w+)\s+(\S.*)?',row)
 if m:sym[int(m.group(1))]=int(m.group(2),16)
count=0
for row in reloc.splitlines():
 m=re.match(r'\s*([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+(R_AVR_\w+)\s+([0-9a-fA-F]{8})\s+(.+?)\s+\+\s+(-?[0-9a-fA-F]+)\s*$',row)
 if not m:continue
 offs,info,typ,symhex,name,addend=m.groups()
 offs=int(offs,16); idx=int(info,16)>>8
 # readelf AVR print: addend of section symbols in HEX.
 addend=int(addend,16) if name=='.text' else int(addend,0)
 target=sym[idx]+addend
 assert 0 <=offs<=len(raw)-2 and 0<=target<len(raw),(offs,typ,target)
 w=int.from_bytes(raw[offs:offs+2],'little')
 if typ=='R_AVR_13_PCREL':
  assert not ((target-offs-2)&1)
  disp=(target-offs-2)//2
  assert -2048<=disp<=2047
  assert (w&0xf000) in (0xc000,0xd000)
  w=(w&0xf000)|(disp&0xfff)
 elif typ in ('R_AVR_LO8_LDI','R_AVR_HI8_LDI'):
  assert w & 0xf000 == 0xe000
  k=(target>>(8 if typ=='R_AVR_HI8_LDI' else 0))&255
  w=(w&0xf0f0)|((k&0xf0)<<4)|(k&0x0f)
 else:
  raise AssertionError(('Unsupported ELF relocation',typ))
 raw[offs:offs+2]=w.to_bytes(2,'little');count+=1
 print(f'{offs:04x} {typ:17s} target={target:04x} value={w:04x}')
assert count==12, count
assert len(raw)<=1024, f'Firmware exceeds 1K: {len(raw)}'
(P/'tiny13_quality_r2_demo.bin').write_bytes(raw)
lines=[]
for addr in range(0,len(raw),16):
 chunk=raw[addr:addr+16]; row=[len(chunk),(addr>>8)&255,addr&255,0,*chunk];row.append((-sum(row))&255)
 lines.append(':'+''.join(f'{v:02X}' for v in row))
lines.append(':00000001FF')
(P/'tiny13_quality_r2_demo.hex').write_text('\n'.join(lines)+'\n')
# Verify .hex roundtrip independently
back=bytearray()
for line in lines[:-1]:
 b=bytes.fromhex(line[1:]);assert (sum(b)&255)==0
 size,address=(b[0],(b[1]<<8)|b[2]);assert address==len(back)
 back+=b[4:4+size]
assert back==raw
print(f'Firmware bytes: {len(raw)}/1024, SRAM variables: 35 bytes (0x60..0x82), sha256: {hashlib.sha256(raw).hexdigest()}')
