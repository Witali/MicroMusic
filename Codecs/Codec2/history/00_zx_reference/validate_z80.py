#!/usr/bin/env python3
from pathlib import Path
import re
HERE=Path(__file__).resolve().parent
origin=0x8000
blob=(HERE/'codec2zx.bin').read_bytes()
mem=bytearray(65536); mem[origin:origin+len(blob)]=blob
# parse symbols from listing
sym={}
in_syms=False
for line in (HERE/'codec2zx.lst').read_text().splitlines():
    if line=='Symbols:': in_syms=True; continue
    if in_syms:
        if not line.strip(): break
        m=re.match(r'(\w+)\s+([0-9A-Fa-f]{4})$',line.strip())
        if m: sym[m.group(1)]=int(m.group(2),16)

R={k:0 for k in 'abcdehl'}; PC=sym['decode_frame']; Z=C=False
stack=[0xffff]  # sentinel return address

def get16(lo,hi): return (R[hi]<<8)|R[lo]
def set16(lo,hi,v): R[lo]=v&255; R[hi]=(v>>8)&255

def rrname(code): return [('b','c'),('d','e'),('h','l'),None][code]

def regget(code):
    if code==6: return mem[get16('l','h')]
    return R[['b','c','d','e','h','l',None,'a'][code]]
def regset(code,v):
    v&=255
    if code==6: mem[get16('l','h')]=v
    else: R[['b','c','d','e','h','l',None,'a'][code]]=v

def alu_flags(v,carry=None):
    global Z,C
    Z=((v&255)==0)
    if carry is not None: C=carry

def s8(x): return x-256 if x>=128 else x

steps=0
while PC!=0xffff and steps<200000:
    steps+=1; op=mem[PC]; PC=(PC+1)&0xffff
    if op==0x00: pass
    elif op==0xC9:
        PC=stack.pop()
    elif op==0xCD:
        lo=mem[PC]; hi=mem[PC+1]; PC+=2; stack.append(PC); PC=lo|(hi<<8)
    elif op==0x18:
        d=s8(mem[PC]); PC+=1; PC=(PC+d)&0xffff
    elif op in (0x20,0x28,0x30,0x38):
        d=s8(mem[PC]); PC+=1
        take={0x20:not Z,0x28:Z,0x30:not C,0x38:C}[op]
        if take: PC=(PC+d)&0xffff
    elif op==0x10:
        d=s8(mem[PC]); PC+=1; R['b']=(R['b']-1)&255
        if R['b']!=0: PC=(PC+d)&0xffff
    elif op==0x2A:
        nn=mem[PC]|(mem[PC+1]<<8); PC+=2; set16('l','h',mem[nn]|(mem[(nn+1)&0xffff]<<8))
    elif op==0x22:
        nn=mem[PC]|(mem[PC+1]<<8); PC+=2; v=get16('l','h'); mem[nn]=v&255; mem[(nn+1)&0xffff]=v>>8
    elif op==0x3A:
        nn=mem[PC]|(mem[PC+1]<<8); PC+=2; R['a']=mem[nn]
    elif op==0x32:
        nn=mem[PC]|(mem[PC+1]<<8); PC+=2; mem[nn]=R['a']
    elif op in (0x01,0x11,0x21,0x31):
        code=(op-1)//0x10; v=mem[PC]|(mem[PC+1]<<8); PC+=2
        if code==0:set16('c','b',v)
        elif code==1:set16('e','d',v)
        elif code==2:set16('l','h',v)
        else: pass
    elif op in (0x09,0x19,0x29,0x39):
        code=(op-9)//0x10; hl=get16('l','h')
        vv=[get16('c','b'),get16('e','d'),hl,0][code]
        s=hl+vv; set16('l','h',s); C=s>0xffff
    elif op==0x23:
        set16('l','h',(get16('l','h')+1)&0xffff)
    elif 0x40<=op<=0x7f and op!=0x76:
        d=(op>>3)&7; s=op&7; regset(d,regget(s))
    elif op in (0x06,0x0e,0x16,0x1e,0x26,0x2e,0x36,0x3e):
        d=(op>>3)&7; regset(d,mem[PC]); PC+=1
    elif op in (0x04,0x0c,0x14,0x1c,0x24,0x2c,0x34,0x3c):
        d=(op>>3)&7; v=(regget(d)+1)&255; regset(d,v); Z=(v==0) # C unchanged
    elif op in (0x05,0x0d,0x15,0x1d,0x25,0x2d,0x35,0x3d):
        d=(op>>3)&7; v=(regget(d)-1)&255; regset(d,v); Z=(v==0)
    elif 0x80<=op<=0x87:
        v=regget(op&7); s=R['a']+v; R['a']=s&255; alu_flags(R['a'],s>255)
    elif op==0xC6:
        v=mem[PC];PC+=1;s=R['a']+v;R['a']=s&255;alu_flags(R['a'],s>255)
    elif 0x90<=op<=0x97:
        v=regget(op&7); old=R['a']; R['a']=(old-v)&255;alu_flags(R['a'],old<v)
    elif op==0xD6:
        v=mem[PC];PC+=1;old=R['a'];R['a']=(old-v)&255;alu_flags(R['a'],old<v)
    elif 0xA0<=op<=0xA7:
        R['a'] &= regget(op&7); alu_flags(R['a'],False)
    elif 0xA8<=op<=0xAF:
        R['a'] ^= regget(op&7); alu_flags(R['a'],False)
    elif 0xB0<=op<=0xB7:
        R['a'] |= regget(op&7); alu_flags(R['a'],False)
    elif 0xB8<=op<=0xBF:
        v=regget(op&7); old=R['a']; alu_flags((old-v)&255,old<v)
    elif op==0xFE:
        v=mem[PC];PC+=1; old=R['a']; alu_flags((old-v)&255,old<v)
    elif op==0xCB:
        cb=mem[PC];PC+=1; code=cb&7; group=cb&0xf8; v=regget(code)
        if 0x20<=cb<=0x27: # SLA
            C=bool(v&0x80); v=(v<<1)&255
        elif 0x38<=cb<=0x3f: # SRL
            C=bool(v&1); v>>=1
        else: raise RuntimeError(f'CB {cb:02x}')
        regset(code,v); Z=(v==0)
    else:
        raise RuntimeError(f'op {op:02x} at {PC-1:04x}')

if PC!=0xffff: raise RuntimeError('did not return')
print('emulated decode_frame steps',steps)
for name in ['voiced','pitch_index','energy_index','pitch_units','base_volume','center0','center1','center2']:
    print(name,mem[sym[name]])
sp=mem[sym['stream_ptr']]|(mem[sym['stream_ptr']+1]<<8)
print('stream ptr',hex(sp),'expected',hex(sym['sample_data']+8))
# Independent parse of first frame
fr=(HERE/'speech.c2zx').read_bytes()[:8]
bits=[(b>>k)&1 for b in fr for k in range(7,-1,-1)]
p=0
def gray(g):
    x=g; x^=x>>1; x^=x>>2; x^=x>>4; return x
def get(n):
    global p
    g=0
    for _ in range(n): g=(g<<1)|bits[p]; p+=1
    return gray(g)
v0=get(1);v1=get(1);pi=get(7);ei=get(5);ix=[get(5) for _ in range(10)]
acc=0; centers=[]
def du(i,x): return ((x+1) if x<8 else (2*x-6)) if i in (3,4,5) else x+1
for i,x in enumerate(ix[:6]):
    acc=min(255,acc+du(i,x))
    if i%2==0: prev=acc
    else: centers.append(min(255,prev+acc))
print('expected',{'voiced':v1,'pitch_index':pi,'energy_index':ei,'centers':centers})
assert mem[sym['voiced']]==v1
assert mem[sym['pitch_index']]==pi
assert mem[sym['energy_index']]==ei
assert [mem[sym[f'center{i}']] for i in range(3)]==centers
assert sp==sym['sample_data']+8
print('VALIDATION OK')
