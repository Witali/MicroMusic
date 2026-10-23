"""Build and execute two CRC32C table generators as genuine 8080 machine code.
Uses independent host Python bitwise generation for comparison.
"""
from pathlib import Path
import sys, time, json
base=Path(__file__).resolve().parent
sys.path.insert(0,str(base))
from intel8080_tools import Assembler, Emulator8080, table_crc32c

class Asm(Assembler):
    @staticmethod
    def op_bytes(mn, args, labels):
        if mn=='JP':
            num=Assembler.number(args[0],labels)
            return [0xF2,num&0xff,num>>8]
        if mn=='PUSH':
            return [0xC5+16*{'B':0,'D':1,'H':2}.get(args[0],0)]
        return Assembler.op_bytes(mn,args,labels)

class EmuRAM(Emulator8080):
    def __init__(self, rom):
        super().__init__(rom)
        self.sign=False
        self.mem=bytearray([0xA5]*65536)
        self.mem[:len(rom)]=rom
        self.written=set()
    def read(self,adr):
        return self.mem[adr&0xFFFF]
    def get(self,r):
        if r==6: return self.read(self.get_hl())
        return self.regs[r]
    def put(self,r,v):
        if r==6:
            adr=self.get_hl()
            if adr < 0x8000 or adr >= 0x8400: raise ValueError(f'Write unexpected RAM address {adr:#x}')
            self.mem[adr]=v&0xff
            self.written.add(adr)
        else: self.regs[r]=v&0xff
    def one(self):
        op=self.mem[self.pc]
        if op==0xF2:  # JP addr (positive: S=0), 10 cycles on 8080
            self.pc+=1; self.steps+=1
            dest=self.w16()
            if not self.sign: self.pc=dest
            self.cycles+=10
            return
        if op==0x24:  # INR H sets sign; independent of CY
            super().one()
            self.sign=bool(self.regs[4]&0x80)
            return
        if 0x70 <= op <= 0x77 and op != 0x76:  # MOV M,r uses 7 cycles
            self.pc += 1; self.steps+=1; self.cycles+=7
            self.put(6,self.get(op & 7))
            return
        if op in (0xC5,0xD5,0xE5):
            self.pc += 1; self.steps+=1; self.cycles+=11
            r=(op>>4)&3
            if r==0: val=(self.regs[0]<<8)|self.regs[1]
            elif r==1: val=(self.regs[2]<<8)|self.regs[3]
            else: val=self.get_hl()
            self.sp=(self.sp-2)&65535
            for ofs,v in ((0,val&0xff),(1,val>>8)):
                adr=(self.sp+ofs)&0xffff
                if not 0x8000<=adr<0x8400:raise ValueError(f'PUSH outside RAM {adr:04x}')
                self.mem[adr]=v
                self.written.add(adr)
            return
        return super().one()

want = table_crc32c()
for file,layout in [('gen_planes_57.asm','planes'),('gen_packed_57.asm','packed')]:
    asm_text=(base/file).read_text()
    rom,written,labels=Asm().assemble(asm_text,0x8000)
    emu=EmuRAM(rom)
    start=time.perf_counter()
    while not emu.halt:
        emu.one()
        if emu.steps>1_000_000:raise RuntimeError('Loop')
    elapsed=time.perf_counter()-start
    got=[]
    for i in range(256):
        if layout=='planes':
            n=sum(emu.mem[0x8000+i+0x100*j]<<(8*j) for j in range(4))
        else:
            n=int.from_bytes(emu.mem[0x8000+i*4:0x8000+i*4+4],'little')
        got.append(n)
    mismatches=[(i,f'{got[i]:08X}',f'{want[i]:08X}') for i in range(256) if got[i]!=want[i]]
    assert emu.written==set(range(0x8000,0x8400)),len(emu.written)
    assert not mismatches,(layout,mismatches[:10])
    # Also check that table produces canonical CRC-32C of "123456789".
    state=0xffffffff
    for ch in b'123456789':
        state=(state>>8)^got[(state^ch)&255]
    assert (state ^ 0xffffffff)==0xE3069283
    (base/file.replace('.asm','.bin')).write_bytes(rom[:len(written)])
    print(f'{file}: CODE={len(written)} bytes CPU={emu.cycles:,} cycles TIME={emu.cycles/3500000*1000:.2f} ms STEPS={emu.steps:,} PASS {len(got)} entries.')
    print(f'   T[0]={got[0]:08X}, T[1]={got[1]:08X}, T[2]={got[2]:08X}, T[255]={got[255]:08X}')
