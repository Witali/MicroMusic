#!/usr/bin/env python3
"""Source-level AVR instruction simulator (cycle-aware) + Codec2 3200 checks.

Not a hardware simulator: it interprets the exact assembly instruction sequence
also assembled into codec2tiny3200.o by LLVM. Input bits crosschecked with
native libcodec2.unpack to guard against a mutually consistent parser bug.
"""
from __future__ import annotations
import re,sys,ctypes,ctypes.util,wave,struct,random,collections,hashlib,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASM=ROOT/'src'/'codec2tiny3200.S'
OUT=ROOT/'audio'
OUT.mkdir(exist_ok=True)


def parse_asm(path=ASM):
    src=path.read_text()
    sym={}
    for n,v in re.findall(r'^\.equ\s+(\w+)\s*,\s*(0x[0-9a-fA-F]+|\d+)',src,flags=re.M):sym[n]=int(v,0)
    inst=[];labels={};addr=0
    for line in src.splitlines():
        line=line.split('/*',1)[0].split('//',1)[0].strip()
        if not line or line.startswith(('.', '*')):continue
        if line.endswith(':'):
            labels[line[:-1]]=len(inst);continue
        if line.startswith('/*') or line.startswith('*/'):continue
        # 'sbiw ..., ...' etc
        parts=line.strip().split(None,1)
        op=parts[0].lower()
        args=[x.strip() for x in parts[1].split(',')] if len(parts)>1 else []
        inst.append((op,args,addr))
        addr+=4 if op in ('sts','lds') else 2
    return inst,labels,sym

class AVR:
    def __init__(self, inst, labels, sym):
        self.inst=inst; self.labels=labels;self.sym=sym
        self.r=[0]*32;self.mem=bytearray(256)
        self.c=self.z=0;self.total=0;self.samples_cycles=[];self.dec_cycles=[];self.val_cache={};self.stkdata=[]
    def val(self, e):
        e=e.strip()
        if e in self.val_cache:return self.val_cache[e]
        for name,value in self.sym.items():e=re.sub(r'\b'+name+r'\b',str(value),e)
        if not re.fullmatch(r'[0-9a-fxA-F+\- ()]+',e):raise Exception('bad expression '+e)
        out=eval(e,{'__builtins__':{}},{})
        self.val_cache[e]=out
        return out
    @staticmethod
    def reg(x):
        assert x[0]=='r',x
        return int(x[1:])
    def run(self,label,max_steps=500000):
        pc=self.labels[label];stk=[];total=0;steps=0
        while True:
            if steps>max_steps:raise RuntimeError('instruction runaway '+label+' pc='+str(pc))
            steps+=1
            op,aa,addr=self.inst[pc];pc+=1
            b=aa
            x=self.reg(b[0]) if b and re.fullmatch(r'r\d+',b[0]) else 0
            r=self.r
            cycles=1
            if op in ('ldi','subi','cpi'):
                v=self.val(b[1])&255
                if op=='ldi':r[x]=v
                else:
                    a=r[x]; d=(a-v)&255
                    self.c=int(a<v);self.z=int(d==0)
                    if op=='subi':r[x]=d
            elif op in ('mov','add','adc','sub','cp','and','or','eor'):
                y=self.reg(b[1]);a=r[x]; v=r[y]
                if op=='mov':r[x]=v
                elif op in ('add','adc'):
                    s=a+v+(self.c if op=='adc' else 0)
                    self.c=int(s>255);r[x]=s&255;self.z=int(r[x]==0)
                elif op in ('sub','cp'):
                    d=(a-v)&255;self.c=int(a<v);self.z=int(d==0)
                    if op=='sub':r[x]=d
                else:
                    if op=='and':r[x]=a&v
                    elif op=='or':r[x]=a|v
                    else:r[x]=a^v
                    self.z=int(r[x]==0)
            elif op in ('clr','lsl','lsr','rol','ror','inc','dec','tst'):
                a=r[x]
                if op=='clr': r[x]=0
                elif op=='lsl':self.c=int(a&128!=0);r[x]=(a<<1)&255
                elif op=='lsr':self.c=a&1;r[x]=a>>1
                elif op=='rol':
                    carry=self.c;self.c=int(bool(a&0x80));r[x]=((a<<1)|carry)&255
                elif op=='ror':nc=a&1;r[x]=((self.c<<7)|(a>>1))&255;self.c=nc
                elif op=='inc':r[x]=(a+1)&255
                elif op=='dec':r[x]=(a-1)&255
                self.z=int(r[x]==0)
            elif op in ('lds','sts'):
                if op=='lds':r[x]=self.mem[self.val(b[1])]
                else:self.mem[self.val(b[0])]=r[self.reg(b[1])]
                cycles=2
            elif op=='ld':
                assert b[1]=='X'
                addr=r[26] | (r[27]<<8)
                assert addr<len(self.mem)
                r[x]=self.mem[addr]
                cycles=2
            elif op=='push':
                self.stkdata.append(r[x]);cycles=2
            elif op=='pop':
                r[x]=self.stkdata.pop();cycles=2
            elif op=='in':
                a=self.val(b[1]);r[x]= ((self.z<<1)|self.c) if a==0x3f else self.mem[0x20+a]
            elif op=='out':
                a=self.val(b[0]);v=r[self.reg(b[1])]
                if a==0x3f:self.c=v&1;self.z=(v>>1)&1
                else:self.mem[0x20+a]=v
            elif op=='sei':
                pass
            elif op=='reti':
                total+=4;self.total+=total;return total
            elif op=='adiw':
                assert self.reg(b[0])==26
                a=(r[26]|r[27]<<8)+self.val(b[1]);a&=65535
                r[26]=a&255;r[27]=a>>8
                self.z=int(a==0);cycles=2
            elif op in ('breq','brne','brlo','brcs','brcc'):
                ok={'breq':self.z==1,'brne':self.z==0,'brlo':self.c==1,'brcs':self.c==1,'brcc':self.c==0}[op]
                if ok:pc=self.labels[b[0]];cycles=2
            elif op=='rjmp':pc=self.labels[b[0]];cycles=2
            elif op=='rcall':stk.append(pc);pc=self.labels[b[0]];cycles=3
            elif op=='ret':
                cycles=4
                if stk:pc=stk.pop()
                else:
                    total+=cycles;self.total+=total
                    return total
            elif op in ('sbrc','sbrs'):
                rd=self.reg(b[0]); mask=1<<self.val(b[1])
                skip=((r[rd]&mask)==0) if op=='sbrc' else ((r[rd]&mask)!=0)
                if skip:
                    cycles=2 if self.inst[pc][0] not in ('sts','lds') else 3
                    pc+=1
            else:raise RuntimeError(f'unsupported instruction {op} {b} at {addr:#x}')
            total+=cycles

# Independent reference implementation uses *different* extraction logic
# and Python arithmetic rather than instructions, and cross-checks libcodec2.
def fields(frame:bytes):
    assert len(frame)==8
    bitpos=0
    def take(n):
        nonlocal bitpos
        gr=0
        for _ in range(n):
            gr=(gr<<1)|((frame[bitpos>>3]>>(7-(bitpos&7)))&1)
            bitpos+=1
        z=gr
        z^=z>>1; z^=z>>2;z^=z>>4
        return z
    v0=take(1);v1=take(1);p=take(7);e=take(5)
    lsp=[take(5) for _ in range(10)]
    assert bitpos==64
    return v0,v1,p,e,lsp

def expected_steps(f):
    v0,v1,p,e,lsp=f
    f0=2+(p>>3)-(p>>6)
    pos=0;steps=[]
    for i,d in enumerate(lsp[:6]):
        d=d+1 if i not in (3,4,5) or d<8 else 2*d-6
        pos=(pos+d)&255
        if i%2==0:prev=pos
        else:
            desired=(pos+prev)>>1
            v=0
            while v+f0<=desired:v+=f0
            if 2*(desired-v)>=f0:v+=f0
            if not v:v=f0
            steps.append((205*v)&65535)
    return steps


def test():
    inst,labels,sym=parse_asm()
    print('Instructions:',len(inst),'assembly bytes:',max(a for _,_,a in inst)+2)
    sim=AVR(inst,labels,sym)
    assert sim.run('codec2tiny_init')>0
    L=ctypes.CDLL(ctypes.util.find_library('codec2'))
    L.unpack.argtypes=[ctypes.POINTER(ctypes.c_ubyte),ctypes.POINTER(ctypes.c_uint),ctypes.c_uint]
    L.unpack.restype=ctypes.c_int
    L.lspd_bits.argtypes=[ctypes.c_int];L.lspd_bits.restype=ctypes.c_int
    assert [L.lspd_bits(i) for i in range(10)]==[5]*10
    src=[]
    for f in ['speech.c2zx','codec2_3200_8byte_frames.bin']:
        p=(ROOT/'tests'/f)
        if p.exists():src.extend([(f,p.read_bytes()[i:i+8]) for i in range(0,p.stat().st_size,8)])
    assert src
    src+= [('random',random.Random(i).randbytes(8)) for i in range(10)]
    mismatch=[];dcycles=[];scycles=[];decoded_wav=[];fieldset=[]
    for name,frame in src:
        d=fields(frame)
        raw=(ctypes.c_ubyte*8)(*frame)
        off=ctypes.c_uint(0)
        actual=[L.unpack(raw,ctypes.byref(off),n) for n in [1,1,7,5]+[5]*10]
        assert list(d[:4])+d[4]==actual,(name,d,actual)
        sim.mem[0x60:0x68]=frame
        c=sim.run('codec2tiny_decode_frame');dcycles.append(c)
        if (sim.mem[0x68],sim.mem[0x69],sim.mem[0x6a],sim.mem[0x6b])!=d[:4]:mismatch.append((name,'fields',d))
        steps=[sim.mem[0x6e+2*i]|sim.mem[0x6f+2*i]<<8 for i in range(3)]
        exp=expected_steps(d)
        if steps!=exp:mismatch.append((name,'step',exp,steps,d))
        for j in range(160):
            c=sim.run('codec2tiny_sample');scycles.append(c)
            if name!='random':decoded_wav.append(sim.r[16])
    print('Frames',len(src),'parse errors',len(mismatch),'cycles per decode min/max',min(dcycles),max(dcycles),'per sample min/max',min(scycles),max(scycles))
    if mismatch:raise AssertionError(mismatch[:5])
    print('Worst complete frame upper-bound:',max(dcycles)+160*max(scycles),'cycles, available=192000')
    # Compute WAV separately per file to avoid combining different voices and random transitions.
    for filename in ['speech.c2zx','codec2_3200_8byte_frames.bin']:
        data=(ROOT/'tests'/filename).read_bytes()
        sim=AVR(inst,labels,sym);sim.run('codec2tiny_init')
        pcm=[]
        for i in range(0,len(data),8):
            sim.mem[0x60:0x68]=data[i:i+8]
            sim.run('codec2tiny_decode_frame')
            for s in range(160):
                sim.run('codec2tiny_sample')
                pcm.append((sim.r[16]-128)<<8)
        out=OUT/(filename+'.avr_sim.wav')
        with wave.open(str(out),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
            w.writeframes(struct.pack('<'+'h'*len(pcm),*pcm))
        print('Saved',out,'samples',len(pcm),'sha256',hashlib.sha256(out.read_bytes()).hexdigest()[:16])
    (ROOT/'tests'/'cycles.txt').write_text(f'frames={len(src)}\nparse_min={min(dcycles)}\nparse_max={max(dcycles)}\nsample_min={min(scycles)}\nsample_max={max(scycles)}\nworst_conservative={max(dcycles)+160*max(scycles)}\n')
    print('PASS')

if __name__=='__main__':
    test()
