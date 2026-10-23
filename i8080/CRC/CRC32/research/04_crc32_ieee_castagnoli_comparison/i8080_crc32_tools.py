"""Assembler + instruction emulator for RAM-less 8080 CRC32 ROM verifier.
Based on the self-contained 8080 subset used by earlier dual-CRC16 research.
Model includes POP-from-ROM, DAD SP, XCHG, RAL, DI/EI and cycle counts.
"""
from __future__ import annotations
import re
from pathlib import Path

R={'B':0,'C':1,'D':2,'E':3,'H':4,'L':5,'M':6,'A':7}

def val(s,symbols):
    s=s.strip().upper()
    if s in symbols:return symbols[s]
    if s.endswith('H'):return int(s[:-1],16)
    if s.startswith('0X'):return int(s,16)
    return int(s)

def instr(s,symbols):
    parts=s.strip().upper().split(None,1)
    op=parts[0];a=parts[1].strip() if len(parts)>1 else ''
    if op=='ORG':return ('org',val(a,symbols))
    if op=='POP':return bytes([{'B':0xC1,'D':0xD1,'H':0xE1,'PSW':0xF1}[a]])
    if op=='MOV':
        x,y=[z.strip() for z in a.split(',')]
        return bytes([0x40+(R[x]<<3)+R[y]])
    if op=='MVI':
        x,y=[z.strip() for z in a.split(',')]
        return bytes([0x06+R[x]*8,val(y,symbols)&255])
    if op=='LXI':
        x,y=[z.strip() for z in a.split(',')]
        u=val(y,symbols)
        return bytes([{'B':0x01,'D':0x11,'H':0x21,'SP':0x31}[x],u&255,(u>>8)&255])
    if op in ('XRA','ORA','ADD','ADC','ANA','SUB','SBB'):
        return bytes([{'XRA':0xA8,'ORA':0xB0,'ADD':0x80,'ADC':0x88,'ANA':0xA0,'SUB':0x90,'SBB':0x98}[op]+R[a]])
    if op in ('ANI','XRI','ORI','ACI','SUI','SBI','CPI'):
        return bytes([{'ANI':0xE6,'XRI':0xEE,'ORI':0xF6,'ACI':0xCE,'SUI':0xD6,'SBI':0xDE,'CPI':0xFE}[op],val(a,symbols)&255])
    if op in ('JNZ','JZ','JNC','JC','JMP'):
        u=val(a,symbols)
        return bytes([{'JNZ':0xC2,'JZ':0xCA,'JNC':0xD2,'JC':0xDA,'JMP':0xC3}[op],u&255,(u>>8)&255])
    if op in ('DCR','INR'):
        return bytes([({'DCR':0x05,'INR':0x04}[op])+R[a]*8])
    if op in ('DAD','INX','DCX'):
        p={'B':0,'D':1,'H':2,'SP':3}[a]
        return bytes([{'DAD':0x09,'INX':0x03,'DCX':0x0B}[op]+p*16])
    single={'DAA':0x27,'HLT':0x76,'EI':0xFB,'DI':0xF3,'XCHG':0xEB,'NOP':0,'CMA':0x2F,'RLC':0x07,'RRC':0x0F,'RAL':0x17,'RAR':0x1F,'STC':0x37,'CMC':0x3F}
    if op in single: return bytes([single[op]])
    raise ValueError('Unknown instruction '+s)

def assemble(source):
    rows=[]
    for line in source.splitlines():
        line=line.partition(';')[0].strip()
        if not line:continue
        if ':' in line:
            label,_,line=line.partition(':')
            label=label.strip().upper();line=line.strip()
        else:label=None
        rows.append((label,line))
    labels={}
    for phase in range(2):
        pc=0;out=bytearray()
        for label,line in rows:
            if label:
                if phase==0:labels[label]=pc
                else:assert labels[label]==pc
            if not line:continue
            if phase==0 and line.upper().split()[0]!='ORG':
                try:bb=instr(line,labels)
                except (ValueError,KeyError):
                    bb=instr(re.sub(r'(?i)\b(?:JNZ|JZ|JNC|JC|JMP)\s+[A-Za-z]\w*\b','JMP 0000H',line),labels)
            else:bb=instr(line,labels)
            if isinstance(bb,tuple):
                pc=bb[1]
                while len(out)<pc:out.append(0xFF)
            else:
                if pc!=len(out):raise ValueError((pc,len(out)))
                out.extend(bb);pc+=len(bb)
    return bytes(out),labels

TIMINGS={**{x:5 for x in range(0x40,0x80) if x!=0x76},
         **{x:4 for x in range(0x80,0xC0) if x&7!=6},
         0x00:4,0x06:7,0x0E:7,0x16:7,0x1E:7,0x26:7,0x2E:7,0x3E:7,
         0x01:10,0x11:10,0x21:10,0x31:10,
         0xE1:10,0x13:5,0x03:5,0x23:5,0x33:5,
         0x09:10,0x19:10,0x29:10,0x39:10,
         0x05:5,0x0D:5,0x15:5,0x1D:5,0x25:5,0x2D:5,0x3D:5,
         0x04:5,0x0C:5,0x14:5,0x1C:5,0x24:5,0x2C:5,0x34:5,0x3C:5,
         0xC2:10,0xCA:10,0xD2:10,0xDA:10,0xC3:10,
         0xE6:7,0xEE:7,0xF6:7,0xCE:7,0xD6:7,0xDE:7,0xFE:7,
         0xAF:4,0xFB:4,0xF3:4,0x76:7,0x27:4,0xEB:4,0x2F:4,0x07:4,0x0F:4,0x17:4,0x1F:4,0x37:4,0x3F:4}

def crc32(data,poly=0x04C11DB7,init=0xFFFFFFFF):
    c=init
    for b in data:
        c ^= b<<24
        for _ in range(8):
            c=(((c<<1)^(poly if c & 0x80000000 else 0))&0xFFFFFFFF)
    return c

def patch_rom(code,poly=0x04C11DB7,fill=0xff):
    assert len(code)<65532
    rom=bytearray([fill])*65536
    rom[:len(code)]=code
    rom[-4:]=crc32(rom[:-4],poly).to_bytes(4,'big')
    assert crc32(rom,poly)==0
    return bytes(rom)

def emulate(rom,trace=False,max_steps=16000000):
    assert len(rom)==65536
    r=[0xA5]*8
    CY=False;Z=False;INTE=False
    PC=0;SP=0xBABE;t=0;steps=0;reads=0
    visited=bytearray(65536) if trace else None
    while steps<max_steps:
        addr=PC;op=rom[PC];PC=(PC+1)&65535
        t+=TIMINGS[op];steps+=1
        if op==0x76:
            return {'cycles':t,'instructions':steps,'INTE':INTE,
                    'CRC32':(r[0]<<24)|(r[1]<<16)|(r[2]<<8)|r[3],
                    'SP':SP,'PC':PC,'rom_reads':reads,
                    'unique_reads':sum(visited) if trace else None}
        elif op==0xFB:INTE=True
        elif op==0xF3:INTE=False
        elif 0x40<=op<0x80:
            x=(op>>3)&7;y=op&7;assert x!=6 and y!=6
            r[x]=r[y]
        elif op in (0x06,0x0E,0x16,0x1E,0x26,0x2E,0x3E):
            r[(op>>3)&7]=rom[PC];PC=(PC+1)&65535
        elif op in (0x01,0x11,0x21,0x31):
            lo=rom[PC];hi=rom[(PC+1)&65535];PC=(PC+2)&65535
            if op==0x31:SP=(hi<<8)|lo
            else:
                i={0x01:0,0x11:2,0x21:4}[op];r[i]=hi;r[i+1]=lo
        elif op==0xE1:
            r[5]=rom[SP]
            if trace:
                assert not visited[SP], f'Duplicate read {SP:04x}'
                visited[SP]=1
            SP=(SP+1)&65535
            r[4]=rom[SP]
            if trace:
                assert not visited[SP], f'Duplicate read {SP:04x}'
                visited[SP]=1
            SP=(SP+1)&65535;reads+=2
        elif op==0xEB:
            r[2],r[4]=r[4],r[2]
            r[3],r[5]=r[5],r[3]
        elif op==0x29:
            v=((r[4]<<8)|r[5])*2
            CY=bool(v&0x10000);v&=0xffff;r[4]=v>>8;r[5]=v&255
        elif op==0x39:
            v=((r[4]<<8)|r[5])+SP
            CY=bool(v&0x10000);v&=0xffff;r[4]=v>>8;r[5]=v&255
        elif op==0x17:
            v=(r[7]<<1)|int(CY);CY=bool(v&0x100);r[7]=v&255
        elif op==0x2F:r[7]^=0xff
        elif 0xA8<=op<=0xAF:
            r[7]^=r[op&7];CY=False;Z=r[7]==0
        elif 0xB0<=op<=0xB7:
            r[7]|=r[op&7];CY=False;Z=r[7]==0
        elif 0x80<=op<=0x87:
            v=r[7]+r[op&7];r[7]=v&255;CY=v>255;Z=r[7]==0
        elif op==0xFE:
            v=r[7]-rom[PC];PC=(PC+1)&65535;CY=v<0;Z=(v==0)
        elif op==0xEE:
            r[7]^=rom[PC];PC=(PC+1)&65535;CY=False;Z=r[7]==0
        elif op in (0x05,0x0D,0x15,0x1D,0x25,0x2D,0x3D):
            i=(op>>3)&7;r[i]=(r[i]-1)&255;Z=r[i]==0
        elif op in (0x04,0x0C,0x14,0x1C,0x24,0x2C,0x3C):
            i=(op>>3)&7;r[i]=(r[i]+1)&255;Z=r[i]==0
        elif op in (0xC2,0xCA,0xD2,0xDA,0xC3):
            dst=rom[PC]|(rom[(PC+1)&65535]<<8);PC=(PC+2)&65535
            if {0xC2:not Z,0xCA:Z,0xD2:not CY,0xDA:CY,0xC3:True}[op]:PC=dst
        else:raise AssertionError(f'Unimplemented opcode {op:02x} at {addr:04x}')
    raise TimeoutError(f'No HLT after {steps} instructions; PC {PC:04x}; SP={SP:04x}; reads={reads}')

if __name__=='__main__':
    for profile,poly in [('crc32_mpeg2_8080',0x04C11DB7),('crc32c_msb_8080',0x1EDC6F41)]:
        src=Path(__file__).with_name(profile+'.asm').read_text()
        code,labels=assemble(src)
        Path(__file__).with_name(profile+'.bin').write_bytes(code)
        print(profile,len(code),'bytes',labels)
        img=patch_rom(code,poly)
        Path(__file__).with_name(profile+'_ROM_64KiB.bin').write_bytes(img)
        print(' footer',img[-4:].hex(),'expected zero',crc32(img,poly))
        result=emulate(img,trace=True)
        print(' GOOD',result)
        assert result['CRC32']==0 and result['INTE'] and result['rom_reads']==65536 and result['unique_reads']==65536 and result['SP']==0
        bad=bytearray(img);bad[0x2345]^=0x10
        result=emulate(bad)
        print(' BAD ',result)
        assert result['CRC32']==crc32(bad,poly)!=0 and not result['INTE']
