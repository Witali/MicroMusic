"""Small fail-closed assembler for the AVR subset used by this project.

Implements the project's GNU AVR source, not arbitrary AVR assembly. The
encoder was validated against the original GNU/LLVM-produced images before
those obsolete firmware versions were removed from the working tree.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DEVICE_INCLUDE = (ROOT / 'web-player/native/attiny13a-registers.generated.inc').resolve()
DEFINITION = json.loads((ROOT / 'web-player/lib/attiny13a-registers.json').read_text(encoding='utf-8'))
assert DEFINITION['schema'] == 'micromusic-attiny13a-register-map-v1', 'Unsupported device map schema'
AT13_IO = DEFINITION['maps']['AT13_IO']
AT13_MEMORY = DEFINITION['maps']['AT13_MEMORY']
IO_ADDRESSES = frozenset(AT13_IO.values())


def assemble(path):
    def expand(file):
        source=re.sub(r'/\*.*?\*/','',file.read_text(encoding='utf-8'),flags=re.S)
        lines=[]
        for line in source.splitlines():
            line=line.strip()
            if line.startswith('.include '): lines.extend(expand(file.parent/line.split('"')[1]))
            elif line: lines.append((line, file.resolve()))
        return lines
    lines=expand(Path(path));symbols={};public_symbols={};rows=[];pc=0
    for line, source in lines:
        if line.endswith(':'):
            symbols[line[:-1]]=pc;public_symbols[line[:-1]]=pc
        elif line.startswith(('.section ','.global ')):continue
        elif line.startswith('.set '):
            key,value=line[5:].split(',');key=key.strip()
            symbols[key]=int(value.strip(),0)
            # Imported vendor constants encode instructions, but do not pollute
            # the existing project-label/build-report contract.
            if source != DEVICE_INCLUDE: public_symbols[key]=symbols[key]
        elif line.startswith('.byte '):
            values=line[6:].split(',');rows.append((pc,'bytes',values));pc+=len(values)
        elif line.startswith('.'): raise ValueError(f'Unsupported directive: {line}')
        else:
            rows.append((pc,'instruction',line));pc+=4 if line.split()[0] in {'lds','sts'} else 2
    def value(s):
        s=s.strip()
        if s in symbols:return symbols[s]
        m=re.fullmatch(r'(lo8|hi8)\((\w+)\)',s)
        if m:return (symbols[m[2]]>>(8 if m[1]=='hi8' else 0))&255
        return int(s,0)
    def register(s):
        assert re.fullmatch(r'r(?:[0-9]|[12][0-9]|3[01])',s),s
        return int(s[1:])
    def rr(base,d,r):return base|(d<<4)|(r&15)|((r&16)<<5)
    def encode(line,at):
        op,*a=line.replace(',',' ').split()
        if op in {'nop','cli','sei','ret','reti','set','clt'}:return {'nop':0,'cli':0x94f8,'sei':0x9478,'ret':0x9508,'reti':0x9518,'set':0x9468,'clt':0x94e8}[op]
        if op in {'clr','tst','lsl'}:
            d=register(a[0]);return rr({'clr':0x2400,'tst':0x2000,'lsl':0x0c00}[op],d,d)
        if op in {'mov','add','adc','sub','and','or','eor'}:
            return rr({'mov':0x2c00,'add':0x0c00,'adc':0x1c00,'sub':0x1800,'and':0x2000,'or':0x2800,'eor':0x2400}[op],register(a[0]),register(a[1]))
        if op=='movw':
            d,r=map(register,a);assert d%2==r%2==0
            return 0x0100|(d//2<<4)|r//2
        if op in {'ldi','cpi','subi','ori','andi'}:
            d,k=register(a[0]),value(a[1]);assert 16<=d<=31 and 0<=k<=255
            return {'ldi':0xe000,'cpi':0x3000,'subi':0x5000,'ori':0x6000,'andi':0x7000}[op]|((d-16)<<4)|(k&15)|((k&240)<<4)
        if op in {'inc','dec','com','lsr','asr','ror','swap','push','pop'}:
            return {'inc':0x9403,'dec':0x940a,'com':0x9400,'lsr':0x9406,'asr':0x9405,'ror':0x9407,'swap':0x9402,'push':0x920f,'pop':0x900f}[op]|register(a[0])<<4
        if op in {'lds','sts'}:
            d,address=(register(a[0]),value(a[1])) if op=='lds' else (register(a[1]),value(a[0]))
            assert AT13_MEMORY['RAMSTART']<=address<=AT13_MEMORY['RAMEND'], 'Only ATtiny13A SRAM addresses are supported'
            return ((0x9000 if op=='lds' else 0x9200)|(d<<4))|(address<<16)
        if op in {'rjmp','rcall','breq','brne','brcs','brcc','brtc','brts'}:
            offset=symbols[a[0]]-at-2;assert offset%2==0
            k=offset//2
            if op in {'rjmp','rcall'}:
                assert -2048<=k<=2047
                return (0xc000 if op=='rjmp' else 0xd000)|(k&4095)
            assert -64<=k<=63,(line,at,k)
            return {'breq':0xf001,'brne':0xf401,'brcs':0xf000,'brcc':0xf400,'brtc':0xf406,'brts':0xf006}[op]|((k&127)<<3)
        if op in {'sbrc','sbrs'}:
            d,bit=register(a[0]),value(a[1]);assert 0<=bit<=7
            return (0xfc00 if op=='sbrc' else 0xfe00)|(d<<4)|bit
        if op=='sbi':
            io,bit=map(value,a);assert 0<=io<=31 and 0<=bit<=7
            assert io in IO_ADDRESSES, 'Undefined ATtiny13A I/O address'
            return 0x9a00|(io<<3)|bit
        if op in {'in','out'}:
            d,io=(register(a[0]),value(a[1])) if op=='in' else (register(a[1]),value(a[0]))
            assert 0<=io<=63
            assert io in IO_ADDRESSES, 'Undefined ATtiny13A I/O address'
            return (0xb000 if op=='in' else 0xb800)|(d<<4)|(io&15)|((io&48)<<5)
        if op=='lpm':
            assert a[1] in {'Z','Z+'}
            return 0x9004|(register(a[0])<<4)|(a[1]=='Z+')
        if op=='ld':
            assert a[1] in {'X','X+','-X','Y+'}
            d=register(a[0]);pointer=28 if a[1]=='Y+' else 26
            assert a[1]=='X' or d not in (pointer,pointer+1),'Undefined LD with destination in modified pointer'
            return {'X':0x900c,'X+':0x900d,'-X':0x900e,'Y+':0x9009}[a[1]]|(d<<4)
        if op=='st':
            assert a[0] in {'X','X+','-X','Z+'}
            d=register(a[1]);pointer=30 if a[0]=='Z+' else 26
            assert a[0]=='X' or d not in (pointer,pointer+1),'Undefined ST with source in modified pointer'
            return {'X':0x920c,'X+':0x920d,'-X':0x920e,'Z+':0x9201}[a[0]]|(d<<4)
        raise ValueError(f'Unsupported instruction: {line}')
    rom=bytearray(pc)
    for at,kind,row in rows:
        if kind=='bytes':
            values=[value(v) for v in row];assert all(0<=v<=255 for v in values)
            rom[at:at+len(values)]=bytes(values)
        else:
            size=4 if row.split()[0] in {'lds','sts'} else 2
            rom[at:at+size]=encode(row,at).to_bytes(size,'little')
    if len(rom)%2:rom.append(255)
    return bytes(rom),public_symbols


def verify_sources(root):
    paths=sorted((Path(root)/'ATtiny13A/Music/variants').glob('*/synth.S'))
    assert paths,'No firmware sources'
    for source in paths:
        path=source.parent
        rom,_=assemble(path/'synth.S')
        expected=(path/'synth.bin').read_bytes()
        assert rom==expected,f'Assembler mismatch: {path}'
    return len(paths)


if __name__=='__main__':
    if sys.argv[1:] == ['--verify']:
        print(verify_sources(Path(__file__).resolve().parents[1]),'AVR sources assemble byte-for-byte.')
    else:
        rom,symbols=assemble(sys.argv[1]);Path(sys.argv[2]).write_bytes(rom);print(len(rom),'bytes')
