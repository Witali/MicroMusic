"""Minimal executable machine-code Intel 8080 model, independent of assembler instruction parser.
Supports instructions used by fused CRC-16 checker; checks cycles and read addresses.
"""
from onepass_8080_tools import TIMINGS

def emulate(rom,trace=False,limit=8000000):
    assert len(rom)==65536
    # 8080 registers order B,C,D,E,H,L,[M not register],A
    r=[0]*8
    pc=0;sp=0;z=False;cy=False;inte=False; cycles=0;reads=0;steps=0
    visited=bytearray(65536) if trace else None
    for steps in range(1,limit+1):
        currentpc=pc
        op=rom[pc];pc=(pc+1)&65535
        if op not in TIMINGS:raise AssertionError(('Missing timing',pc,op))
        cycles+=TIMINGS[op]
        if op==0x76:
            return dict(cycles=cycles,steps=steps,inte=inte,bc=(r[0]<<8)|r[1],de=(r[2]<<8)|r[3],
                sp=sp,reads=reads,unique_reads=sum(visited) if visited is not None else None,
                pc=pc)
        elif op==0xF3:inte=False
        elif op==0xFB:inte=True
        elif 0x40<=op<0x80:
            assert (op&7)!=6 and ((op>>3)&7)!=6
            r[(op>>3)&7]=r[op&7]
        elif op in (0x01,0x11,0x21,0x31):
            lo=rom[pc];hi=rom[(pc+1)&65535];pc=(pc+2)&65535
            if op==0x31:sp=(hi<<8)|lo
            else:
                idx= ((op>>4)*2)
                r[idx]=hi;r[idx+1]=lo
        elif op in (0x06,0x0E,0x16,0x1E,0x26,0x2E,0x3E):
            r[(op>>3)&7]=rom[pc];pc=(pc+1)&65535
        elif op==0xF1:  # POP PSW reads two bytes, A <- (SP+1), F <- (SP)
            F=rom[sp]; addr=(sp+1)&65535;r[7]=rom[addr]
            if visited is not None:
                if visited[addr]:raise AssertionError(('repeat read',addr))
                visited[addr]=1
            reads+=1;sp=(sp+2)&65535
            cy=bool(F&1);z=bool(F&0x40)
        elif op==0x3B: sp=(sp-1)&65535
        elif op==0x39:  # DAD SP
            v=(r[4]<<8)|r[5];u=v+sp;cy=u>65535;r[4]=(u>>8)&255;r[5]=u&255
        elif op==0x23:  # INX H
            v=((r[4]<<8)|r[5])+1;v&=65535;r[4]=v>>8;r[5]=v&255
        elif op in (0x04,0x0C,0x14,0x1C,0x24,0x2C,0x3C):
            idx=(op>>3)&7;r[idx]=(r[idx]+1)&255;z=r[idx]==0
        elif op in range(0xA8,0xB0): r[7]^=r[op&7];z=r[7]==0;cy=False
        elif op in range(0xB0,0xB8): r[7]|=r[op&7];z=r[7]==0;cy=False
        elif op==0x87:
            u=2*r[7];r[7]=u&255;cy=u>255;z=r[7]==0
        elif op==0x07:
            u=r[7];cy=bool(u&0x80);r[7]=((u<<1)|(u>>7))&255
        elif op==0x0F:
            u=r[7];cy=bool(u&0x01);r[7]=((u>>1)|(u<<7))&255
        elif op==0x1F:  # RAR rotates A right through CY (ANI cleared CY before this)
            u=r[7];oldcy=cy;cy=bool(u&1);r[7]=((u>>1)|(0x80 if oldcy else 0))&255
        elif op==0xE6:
            r[7]&=rom[pc];pc=(pc+1)&65535;z=r[7]==0;cy=False
        elif op in (0xC2,0xCA,0xD2,0xDA,0xC3):
            dest=rom[pc]|(rom[(pc+1)&65535]<<8);pc=(pc+2)&65535
            if {0xC2:not z,0xCA:z,0xD2:not cy,0xDA:cy,0xC3:True}[op]:pc=dest
        else:raise AssertionError(('unknown opcode',hex(currentpc),hex(op)))
    raise TimeoutError(f'no HLT within {limit} steps')
