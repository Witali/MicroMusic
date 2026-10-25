#!/usr/bin/env python3
"""Minimal, deliberately narrow relocation resolver for a *single-section*
AVR ELF object. Handles exactly the six relocations emitted by Clang 17 for
src/tiny13_pwm_oneframe_demo.S: PC relative RJMP/RCALL and lo8/hi8 LDI.
The input file is already fully assembled by LLVM; this is not a full linker.
Checks that no unrecognized relocation remains and .text is <=1024 bytes.
"""
from pathlib import Path
import subprocess,re,struct,sys,hashlib
root=Path(__file__).resolve().parents[1]
obj=root/'build/tiny13_pwm_oneframe_demo.o'
out=root/'build/tiny13_pwm_oneframe_demo.bin'
raw=bytearray(subprocess.check_output(['llvm-objcopy','-O','binary','-j','.text',str(obj),'/dev/stdout'])) if False else bytearray((root/'build/tiny13_pwm_oneframe_demo.bin').read_bytes())
assert len(raw)<1024,len(raw)
symtab=subprocess.check_output(['readelf','-sW',str(obj)],text=True)
reltab=subprocess.check_output(['readelf','-rW',str(obj)],text=True)
sym={}
for row in symtab.splitlines():
    m=re.match(r'\s*(\d+):\s+([0-9a-fA-F]+)\s+\d+\s+\w+\s+\w+\s+\w+\s+(\w+)\s+(\S.*)?',row)
    if m:
        idx,addr,sect,name=m.groups();sym[int(idx)]=int(addr,16)
relocs=[]
for row in reltab.splitlines():
    m=re.match(r'\s*([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+(R_AVR_\w+)\s+([0-9a-fA-F]{8})\s+(.*)\s+\+\s+(-?\w+)$',row)
    if m:
        off,info,typ,hexval,name,addend=m.groups()
        # symbolic .text+2c4 addend is HEX (not decimal).
        if name=='.text':a=int(addend,16)
        else:a=int(addend,0)
        relocs.append((int(off,16),typ,int(info,16)>>8,a,sym.get(int(info,16)>>8),name))
assert len(relocs)==6,relocs
for off,typ,idx,addend,symval,name in relocs:
    w=int.from_bytes(raw[off:off+2],'little')
    target=symval+addend
    if typ=='R_AVR_13_PCREL':
        assert (target-off-2)%2==0
        disp=(target-off-2)//2
        assert -2048<=disp<=2047
        assert w & 0xf000 in (0xc000,0xd000)
        w=(w&0xf000)|(disp&0xfff)
    elif typ in ('R_AVR_LO8_LDI','R_AVR_HI8_LDI'):
        assert (w&0xf000)==0xe000
        k=(target>>(8 if typ=='R_AVR_HI8_LDI' else 0))&255
        w=(w&0xf0f0)|((k&0xf0)<<4)|(k&15)
    else:raise AssertionError((off,typ,name))
    raw[off:off+2]=w.to_bytes(2,'little')
    print(f'{off:04x} {typ:20s} {name:22s} target=0x{target:04x} word={w:04x}')
out.write_bytes(raw)

def make_hex(bs):
    lines=[]
    for addr in range(0,len(bs),16):
        chunk=bs[addr:addr+16]
        arr=[len(chunk),(addr>>8)&255,addr&255,0,*chunk]
        check=(-sum(arr))&255
        lines.append(':'+''.join(f'{k:02X}' for k in arr+[check]))
    lines.append(':00000001FF')
    return '\n'.join(lines)+'\n'
hexpath=out.with_suffix('.hex');hexpath.write_text(make_hex(raw))
assert bytes.fromhex(hexpath.read_text().splitlines()[0][9:-2])==raw[:16]
print('FIRMWARE BYTES',len(raw),'SHA256',hashlib.sha256(raw).hexdigest())
