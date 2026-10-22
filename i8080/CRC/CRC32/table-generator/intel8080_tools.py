#!/usr/bin/env python3
"""Minimal self-contained 8080 assembler, emulator and CRC32C reference.
Only the generated firmware goes in EPROM; reference helpers run on host.
"""
from __future__ import annotations
import re
POLY=0x82F63B78
INIT=0xffffffff
REGS={'B':0,'C':1,'D':2,'E':3,'H':4,'L':5,'M':6,'A':7}
PAIRS={'B':0,'D':1,'H':2,'SP':3}

def crc_raw(data: bytes, seed=INIT):
    c = seed
    for b in data:
        c ^= b
        for i in range(8):
            c = (c >> 1) ^ (POLY if c & 1 else 0)
    return c & 0xFFFFFFFF

def crc32c(data: bytes):
    return crc_raw(data) ^ INIT

class Assembler:
    def __init__(self):
        self.labels = {}

    @staticmethod
    def number(text, labels):
        s = text.strip().upper()
        if s in labels:
            return labels[s]
        if s.endswith('H') and re.fullmatch(r'[0-9A-F]+H', s):
            return int(s[:-1], 16)
        if s.startswith('0X'):
            return int(s, 16)
        if s.isdigit():
            return int(s)
        raise ValueError('Unknown constant: '+repr(text))

    @staticmethod
    def op_bytes(mn, args, labels):
        # mn and args are upper case; accepts unresolved labels only if pass1=False.
        def n(i): return Assembler.number(args[i], labels)
        if mn == 'DB':
            return [Assembler.number(x, labels) for x in args]
        if mn == 'LXI':
            return [0x01 + 16*PAIRS[args[0]], n(1)&255, n(1)>>8]
        if mn == 'MVI':
            return [0x06 + 8*REGS[args[0]], n(1)]
        if mn == 'MOV':
            assert args[0] != 'M' or args[1] != 'M'
            return [0x40 + 8*REGS[args[0]] + REGS[args[1]]]
        if mn == 'POP':
            return [0xC1 + 16*PAIRS[args[0]]]
        if mn in ('JMP','JNZ','JNC'):
            return [{'JMP':0xC3, 'JNZ':0xC2, 'JNC':0xD2}[mn],n(0)&255,n(0)>>8]
        if mn == 'CPI': return [0xFE, n(0)]
        if mn == 'XRI': return [0xEE, n(0)]
        if mn == 'XRA': return [0xA8 + REGS[args[0]]]
        if mn == 'ORA': return [0xB0 + REGS[args[0]]]
        if mn == 'INR': return [0x04 + REGS[args[0]]*8]
        if mn == 'DCR': return [0x05 + REGS[args[0]]*8]
        if mn == 'DAD': return [0x09 + 16*PAIRS[args[0]]]
        zero = {'DI':0xF3,'EI':0xFB,'RAR':0x1F,'RRC':0x0F, 'SPHL':0xF9, 'HLT':0x76}
        if mn in zero: return [zero[mn]]
        raise ValueError('Unknown 8080 mnemonic: '+mn)

    @staticmethod
    def lines(src):
        for line in src.splitlines():
            s = line.split(';',1)[0].strip()
            if not s: continue
            label = None
            if ':' in s:
                label, s = s.split(':',1)
                label = label.strip().upper()
                s = s.strip()
            if not s:
                yield label,None,[]
                continue
            parts=s.split(None,1)
            mn=parts[0].upper()
            args=[x.strip().upper() for x in parts[1].split(',')] if len(parts)>1 else []
            yield label,mn,args

    def assemble(self, source, size):
        parsed=list(self.lines(source))
        pc=0
        for label,mn,args in parsed:
            if label is not None:
                assert label not in self.labels, label
                self.labels[label]=pc
            if mn is None: continue
            if mn=='ORG': pc=self.number(args[0],self.labels); continue
            if mn=='END': break
            if mn=='DB': pc+=len(args); continue
            if mn in ('JNZ','JMP','JNC'):
                pc+=3
                continue
            pc+=len(self.op_bytes(mn,args,self.labels))
        rom=bytearray([255]*size)
        written=set()
        pc=0
        for label,mn,args in parsed:
            if mn is None: continue
            if mn=='ORG': pc=self.number(args[0],self.labels); continue
            if mn=='END': break
            bs=self.op_bytes(mn,args,self.labels)
            for v in bs:
                if not 0<=v<=255: raise ValueError('Bad byte %r at %04x'%(v,pc))
                if pc<0 or pc>=size: raise ValueError('Outside ROM at %x'%pc)
                if pc in written: raise ValueError('Address overlap at %x'%pc)
                rom[pc]=v
                written.add(pc)
                pc+=1
        return rom, written, self.labels

def ihex(binary: bytes):
    rows=[]
    for address in range(0,len(binary),16):
        frag=binary[address:address+16]
        body=bytes([len(frag),address>>8,(address&255),0])+frag
        ck=(-sum(body))&0xFF
        rows.append(':'+body.hex().upper()+f'{ck:02X}')
    return '\n'.join(rows+[':00000001FF',''])

class Emulator8080:
    """Instruction-focused cycle-counting 8080 emulator, independent golden CRC checked."""
    def __init__(self, rom: bytes):
        self.rom=rom
        self.regs=[0]*8
        self.pc=0
        self.sp=0
        self.z=False
        self.cy=False
        self.enabled=False
        self.cycles=0
        self.steps=0
        self.memory_reads=[]
        self.halt=False

    def read(self, address):
        if not 0<=address<len(self.rom):
            raise RuntimeError('Memory read outside ROM: %04X'%address)
        return self.rom[address]

    def get(self, r):
        if r==6: return self.read((self.regs[4]<<8)|self.regs[5])
        return self.regs[r]

    def put(self, r,val):
        if r==6: raise AssertionError('ROM write attempted')
        self.regs[r]=val&255

    def get_hl(self):return self.regs[4]*256+self.regs[5]
    def set_hl(self,val):self.regs[4]=(val>>8)&255;self.regs[5]=val&255

    def fetch(self):
        val=self.read(self.pc)
        self.pc=(self.pc+1)&65535
        return val

    def w16(self):
        lo=self.fetch();hi=self.fetch();return lo+(hi<<8)

    def one(self):
        op=self.fetch(); self.steps+=1
        r=self.regs
        if op == 0xF3: self.enabled=False; self.cycles+=4
        elif op == 0xFB: self.enabled=True; self.cycles+=4
        elif op == 0x76: self.halt=True;self.cycles+=7
        elif op in (0x01,0x11,0x21,0x31):
            k=(op>>4)&3; v=self.w16()
            if k==3:self.sp=v
            else:r[2*k]=v>>8; r[2*k+1]=v&255
            self.cycles+=10
        elif op in (0xC1,0xD1,0xE1):
            k=(op>>4)&3
            lo=self.read(self.sp);hi=self.read((self.sp+1)&65535)
            self.sp=(self.sp+2)&65535
            r[2*k]=hi;r[2*k+1]=lo
            self.cycles+=10
        elif 0x40 <= op <= 0x7F:
            to=(op>>3)&7;src=op&7
            self.put(to,self.get(src));self.cycles+=7 if src==6 else 5
        elif op in (0xC2,0xD2,0xC3):
            v=self.w16()
            if op==0xC3 or (op==0xC2 and not self.z) or (op==0xD2 and not self.cy):self.pc=v
            self.cycles+=10
        elif (op&0xC7)==0x06:  # MVI
            to=(op>>3)&7
            self.put(to,self.fetch());self.cycles+=7
        elif 0xA8<=op<=0xAF:
            r[7]^=self.get(op&7);self.cy=False;self.z=(r[7]==0)
            self.cycles+=7 if (op&7)==6 else 4
        elif 0xB0<=op<=0xB7:
            r[7]|=self.get(op&7);self.cy=False;self.z=(r[7]==0)
            self.cycles+=7 if (op&7)==6 else 4
        elif op==0xEE:
            r[7]^=self.fetch();self.z=(r[7]==0);self.cy=False;self.cycles+=7
        elif op==0xFE:
            x=self.fetch();self.z=(r[7]==x);self.cy=(r[7]<x);self.cycles+=7
        elif (op&0xC7)==0x04:  # INR
            dest=(op>>3)&7;v=(self.get(dest)+1)&255
            self.put(dest,v);self.z=(v==0);self.cycles+=5
        elif (op&0xC7)==0x05:  # DCR
            dest=(op>>3)&7;v=(self.get(dest)-1)&255
            self.put(dest,v);self.z=(v==0);self.cycles+=5
        elif op in (0x09,0x19,0x29,0x39):
            k=(op>>4)&3
            val=self.sp if k==3 else ((r[2*k]<<8)|r[2*k+1])
            z=self.get_hl()+val;self.set_hl(z&65535);self.cy=(z>65535);self.cycles+=10
        elif op==0x1F:
            old=r[7];r[7]=((old>>1)|((1 if self.cy else 0)<<7));self.cy=bool(old&1);self.cycles+=4
        elif op==0x0F:
            old=r[7];r[7]=((old>>1)|((old&1)<<7));self.cy=bool(old&1);self.cycles+=4
        elif op==0xF9: self.sp=self.get_hl();self.cycles+=5
        else: raise RuntimeError('Unsupported opcode %02X at %04X'%(op,(self.pc-1)&65535))

    def run_to(self, stop_addr, max_steps=10000000):
        while self.pc!=stop_addr and not self.halt:
            if self.steps>max_steps:raise RuntimeError('Emulator exceeded max steps')
            self.one()

    def state_crc(self):
        r=self.regs
        return (r[0]<<24)|(r[1]<<16)|(r[2]<<8)|r[3]


class AsmPlus(Assembler):
    @staticmethod
    def op_bytes(mn,args,labels):
        if mn=='RAL': return [0x17]
        return Assembler.op_bytes(mn,args,labels)

class Emulator(Emulator8080):
    def one(self):
        if self.rom[self.pc]==0x17:  # RAL: Accumulator and carry rotate left
            self.pc=(self.pc+1)&65535
            old=self.regs[7]
            self.regs[7]=((old<<1)&255)|int(self.cy)
            self.cy=bool(old&128)
            self.cycles+=4
            self.steps+=1
        else:
            super().one()
    def state_crc_msb(self):
        r=self.regs
        return (r[2]<<24)|(r[3]<<16)|(r[4]<<8)|r[5]


def table_crc32c():
    """Standard reflected 256-entry lookup table, four 256-byte planes in ROM."""
    t=[]
    for b in range(256):
        c=b
        for _ in range(8):
            c=(c>>1) ^ (POLY if c&1 else 0)
        t.append(c)
    return t

class AssemblerExtended(Assembler):
    @staticmethod
    def op_bytes(mn,args,labels):
        if mn=='CMP': return [0xB8+REGS[args[0]]]
        if mn=='ADI': return [0xC6,Assembler.number(args[0],labels)]
        if mn=='RLC': return [0x07]
        return Assembler.op_bytes(mn,args,labels)

class EmulatorExtended(Emulator8080):
    def one(self):
        op=self.rom[self.pc]
        if op in (0x07,0xC6) or 0xB8<=op<=0xBF:
            self.pc=(self.pc+1)&0xFFFF
            self.steps+=1
            if op==0x07: # RLC
                a=self.regs[7]
                self.regs[7]=((a<<1)&0xFF)|(a>>7)
                self.cy=bool(a&128)
                self.cycles+=4
            elif op==0xC6: # ADI immediate
                value=self.fetch()
                s=self.regs[7]+value
                self.regs[7]=s&255
                self.cy=s>255
                self.z=(s&255)==0
                self.cycles+=7
            else: # CMP register or M (read-only)
                value=self.get(op&7)
                self.z=(self.regs[7]==value)
                self.cy=(self.regs[7]<value)
                self.cycles+=7 if (op&7)==6 else 4
        else: super().one()

    def run_to(self,addresses,max_steps=10000000):
        while self.pc not in addresses and not self.halt:
            if self.steps>max_steps:
                raise RuntimeError('Exceeded max steps: %d at PC=%04X'%(self.steps,self.pc))
            self.one()
