"""Tiny stand-alone Intel 8080 assembler, executable subset simulator, ROM image patcher.
Supports precisely the instruction subset needed for this checksum comparison.
No third-party dependencies. 8080 instruction timings from Intel manual.
"""
from __future__ import annotations
import re
from pathlib import Path

R={'B':0,'C':1,'D':2,'E':3,'H':4,'L':5,'M':6,'A':7}
CYCLE_MAP={0xAF:4,0x57:5,0x5F:5,0x67:5,0x6F:5}

def parse_value(s,symbols):
    s=s.strip().upper()
    if s in symbols:return symbols[s]
    if s.endswith('H'):return int(s[:-1],16)
    if s.startswith('0X'):return int(s,16)
    return int(s)

def instr(s,symbols):
    parts=s.strip().upper().split(None,1)
    op=parts[0]; arg=parts[1].strip() if len(parts)>1 else ''
    if op=='ORG':return ('org',parse_value(arg,symbols))
    if op=='LDAX':return bytes([{'B':0x0A,'D':0x1A}[arg]])
    if op=='MOV':
        lhs,rhs=[x.strip() for x in arg.split(',')]
        return bytes([0x40+(R[lhs]<<3)+R[rhs]])
    if op=='MVI':
        lhs,rhs=[x.strip() for x in arg.split(',')]
        return bytes([0x06+R[lhs]*8, parse_value(rhs,symbols)&255])
    if op=='LXI':
        lhs,rhs=[x.strip() for x in arg.split(',')]
        u=parse_value(rhs,symbols)
        return bytes([{'B':0x01,'D':0x11,'H':0x21,'SP':0x31}[lhs],u&255,(u>>8)&255])
    if op in ['XRA','ORA','ADD','ADC','ANA','SUB','SBB']:
        return bytes([{'XRA':0xA8,'ORA':0xB0,'ADD':0x80,'ADC':0x88,'ANA':0xA0,'SUB':0x90,'SBB':0x98}[op]+R[arg]])
    if op in ['ANI','XRI','ORI','ACI','SUI','SBI']:
        return bytes([{'ANI':0xE6,'XRI':0xEE,'ORI':0xF6,'ACI':0xCE,'SUI':0xD6,'SBI':0xDE}[op],parse_value(arg,symbols)&255])
    if op in ['JNZ','JZ','JNC','JC','JMP']:
        u=parse_value(arg,symbols)
        return bytes([{'JNZ':0xC2,'JZ':0xCA,'JNC':0xD2,'JC':0xDA,'JMP':0xC3}[op],u&255,(u>>8)&255])
    if op in ['DCR','INR']:
        return bytes([({'DCR':0x05,'INR':0x04}[op])+(R[arg]<<3)])
    if op in ['DAD','INX','DCX']:
        p={'B':0,'D':1,'H':2,'SP':3}[arg]
        return bytes([{'DAD':0x09,'INX':0x03,'DCX':0x0B}[op]+p*16])
    if op in ['DAA','HLT','EI','DI','XCHG','XRAA','NOP','CMA','RLC','RRC','RAL','RAR','STC','CMC']:
        return bytes([{'DAA':0x27,'HLT':0x76,'EI':0xFB,'DI':0xF3,'XCHG':0xEB,'XRAA':0xAF,'NOP':0,'CMA':0x2F,'RLC':0x07,'RRC':0x0F,'RAL':0x17,'RAR':0x1F,'STC':0x37,'CMC':0x3F}[op]])
    raise ValueError('Unknown instruction '+s)

def assemble(source):
    rows=[]
    for line in source.splitlines():
        line=line.partition(';')[0].strip()
        if not line:continue
        if ':' in line:
            label,_,line=line.partition(':')
            label=label.strip().upper();line=line.strip()
        else: label=None
        rows.append((label,line))
    labels={}
    for _ in range(2):
        pc=0;out=bytearray()
        for label,line in rows:
            if label:
                if _==0: labels[label]=pc
                elif labels[label]!=pc:raise AssertionError((label,labels[label],pc))
            if not line:continue
            if _==0 and line.upper().split()[0]!='ORG':
                try: bb=instr(line,labels)
                except (ValueError,KeyError):
                    bb=instr(re.sub(r'(?i)\b(?:JNZ|JZ|JNC|JC|JMP)\s+[A-Za-z]\w*\b','JMP 0000H',line),labels)
            else:bb=instr(line,labels)
            if isinstance(bb,tuple):
                pc=bb[1]
                while len(out)<pc: out.append(0xFF)
            else:
                if pc!=len(out):raise ValueError((pc,len(out)))
                out.extend(bb);pc+=len(bb)
    return bytes(out),labels

# T states as per Intel 8080 datasheet
TIMINGS={**{x:5 for x in range(0x40,0x80) if x!=0x76},
**{x:4 for x in range(0x80,0xc0) if x&7!=6},
 0x00:4, 0x06:7,0x0E:7,0x16:7,0x1E:7,0x26:7,0x2E:7,0x3E:7,
 0x01:10,0x11:10,0x21:10,0x31:10,
 0x1A:7, 0x0A:7, 0x13:5,0x03:5,0x23:5,0x33:5,
 0x09:10,0x19:10,0x29:10,0x39:10,
 0x05:5,0x0D:5,0x15:5,0x1D:5,0x25:5,0x2D:5,0x3D:5,
 0x04:5,0x0C:5,0x14:5,0x1C:5,0x24:5,0x2C:5,0x3C:5,
 0xC2:10,0xCA:10,0xD2:10,0xDA:10,0xC3:10,
 0xE6:7,0xEE:7,0xF6:7,0xCE:7,0xD6:7,0xDE:7,
 0xAF:4,0xFB:4,0xF3:4,0x76:7,0x27:4,0xEB:4,0x2F:4,0x07:4,0x0F:4,0x17:4,0x1F:4,0x37:4,0x3F:4}

def crc(data,poly=0x2d):
    crc=0
    for b in data:
        crc^=b<<8
        for _ in range(8):
            crc=((crc<<1)^(poly if crc&0x8000 else 0))&0xffff
    return crc

def patch_rom(binary,poly=0x2d,fill=0xff):
    assert len(binary)<=65534
    rom=bytearray([fill]*65536)
    rom[:len(binary)]=binary
    rom[-2:]=crc(rom[:-2],poly).to_bytes(2,'big')
    assert crc(rom,poly)==0
    return bytes(rom)

def emulate(rom,init=0x91,max_steps=10000000,crc_layout='HL',trace_addresses=False):
    r=[init]*8
    cy=False;z=False;inte=False
    pc=0; t=0;steps=0;reads=0
    visited=bytearray(65536) if trace_addresses else None
    while steps<max_steps:
        op=rom[pc];pc=(pc+1)&65535
        if op not in TIMINGS:raise AssertionError(f'Unimplemented opcode {op:02X} at {pc-1:04X}')
        t+=TIMINGS[op];steps+=1
        if op==0x76:
            idx={'HL':5,'HC':1}[crc_layout]
            return {'cycles':t,'instructions':steps,'INTE':inte,'CRC':(r[4]<<8)|r[idx], 'DE':(r[2]<<8)|r[3], 'rom_reads':reads,'PC':pc,
                    'unique_rom_reads':sum(visited) if visited is not None else None}
        elif op==0xFB:inte=True
        elif op==0xF3:inte=False
        elif 0x40<=op<0x80: r[(op>>3)&7]=r[op&7]
        elif op in (0x06,0x0E,0x16,0x1E,0x26,0x2E,0x3E):
            r[(op>>3)&7]=rom[pc];pc=(pc+1)&65535
        elif op in (0x01,0x11,0x21):
            lo=rom[pc];hi=rom[(pc+1)&65535];pc=(pc+2)&65535
            idx={'0x1':0,'0x11':2,'0x21':4}[hex(op)]
            r[idx]=hi;r[idx+1]=lo
        elif op==0x1A:
            address=(r[2]<<8)|r[3]
            r[7]=rom[address]; reads+=1
            if visited is not None:
                if visited[address]: raise AssertionError(f'Repeated ROM read at {address:04X}')
                visited[address]=1
        elif 0xA8<=op<=0xAF:
            r[7]^=r[op&7];cy=False;z=(r[7]==0)
        elif 0xB0<=op<=0xB7:
            r[7]|=r[op&7];cy=False;z=(r[7]==0)
        elif 0x98<=op<=0x9F:
            v=r[7]-r[op&7]-int(cy)
            r[7]=v&255;cy=v<0;z=(r[7]==0)
        elif op==0x29:
            v=(((r[4]<<8)|r[5])<<1)
            cy=v>65535;v&=65535;r[4]=v>>8;r[5]=v&255
        elif op==0x13:
            v=(((r[2]<<8)|r[3])+1)&65535
            r[2]=v>>8;r[3]=v&255
        elif op in (0x05,0x0D,0x15,0x1D,0x25,0x2D,0x3D):
            i=(op>>3)&7;r[i]=(r[i]-1)&255;z=(r[i]==0)
        elif op in (0x04,0x0C,0x14,0x1C,0x24,0x2C,0x3C):
            i=(op>>3)&7;r[i]=(r[i]+1)&255;z=(r[i]==0)
        elif op==0xC2 or op==0xCA or op==0xD2 or op==0xDA or op==0xC3:
            addr=rom[pc] | (rom[(pc+1)&65535]<<8);pc=(pc+2)&65535
            if {0xC2:not z,0xCA:z,0xD2:not cy,0xDA:cy,0xC3:True}[op]:pc=addr
        elif op==0xE6:
            r[7]&=rom[pc];pc=(pc+1)&65535;cy=False;z=(r[7]==0)
        elif op==0x27:
            # For these programs DAA is only executed after SBB A with 00/CY=0 or FF/CY=1
            if r[7]==0 and not cy:r[7]=0
            elif r[7]==255 and cy:r[7]=0x65
            else:raise ValueError('DAA used beyond supported special-case')
            z=r[7]==0
        elif op==0x00:pass
        else:raise AssertionError(f'Unimplemented opcode {op:02X} at {pc-1:04X}')
    raise TimeoutError('no HLT')

if __name__=='__main__':
    p=Path('/mnt/data/crc16_8080_factorized.asm')
    src=p.read_text(); program,syms=assemble(src)
    print('assembled:',len(program),'bytes',program.hex(' ').upper(),syms)
    p.with_suffix('.bin').write_bytes(program)
    rom=bytearray(patch_rom(program))
    p.with_name('crc16_8080_factorized_demo_64k.bin').write_bytes(rom)
    print('reference CRC footer',rom[-2:].hex())
    r=emulate(rom);print('good',r)
    for addr in (0x100, 0x2345, 0xA000,0xFFFD):
        rom[addr]^=1
        rr=emulate(rom)
        print('bad',hex(addr),rr)
        assert rr['CRC']!=0 and not rr['INTE']
        rom[addr]^=1
    assert r['rom_reads']==65536 and r['CRC']==0 and r['INTE']
