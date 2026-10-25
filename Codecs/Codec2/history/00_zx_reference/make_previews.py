#!/usr/bin/env python3
from pathlib import Path
import ctypes, struct, wave, math
import numpy as np
from scipy.io.wavfile import write
HERE=Path(__file__).resolve().parent
FS=8000; N=160
stream=(HERE/'speech.c2zx').read_bytes()

# 1) Reference Codec2 decoder preview via installed libcodec2.
lib=ctypes.CDLL('/lib/x86_64-linux-gnu/libcodec2.so.1.2')
lib.codec2_create.argtypes=[ctypes.c_int]; lib.codec2_create.restype=ctypes.c_void_p
lib.codec2_destroy.argtypes=[ctypes.c_void_p]
lib.codec2_decode.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_short),ctypes.POINTER(ctypes.c_ubyte)]
c2=lib.codec2_create(0)
out=[]; ob=(ctypes.c_short*N)(); ib=(ctypes.c_ubyte*8)()
for off in range(0,len(stream),8):
    fr=stream[off:off+8]
    for i,v in enumerate(fr): ib[i]=v
    lib.codec2_decode(c2,ob,ib)
    out.extend(int(x) for x in ob)
lib.codec2_destroy(c2)
write(HERE/'reference_codec2.wav',FS,np.asarray(out,dtype=np.int16))

# 2) Approximate preview of the Z80/AY algorithm (not a cycle-accurate AY emulator).
def gray(g):
    x=g; x^=x>>1; x^=x>>2; x^=x>>4; return x

def unpack(fr):
    bits=[(b>>k)&1 for b in fr for k in range(7,-1,-1)]; p=0
    def get(n):
        nonlocal p
        g=0
        for _ in range(n): g=(g<<1)|bits[p]; p+=1
        return gray(g)
    v0=get(1);v1=get(1);pi=get(7);ei=get(5);ix=[get(5) for _ in range(10)]
    return v1,pi,ei,ix

def du(i,x):
    return (x+1 if x<8 else 2*x-6) if i in (3,4,5) else x+1

def snap(center_u,pitch_u):
    if pitch_u<=0:return max(1,center_u)
    n=max(1,int(center_u/pitch_u+0.5))
    return min(255,n*pitch_u)

energy=[round(15*((i/31)**1.45)) if i else 0 for i in range(32)]
AY=1773400.0
phase=[0.,0.,0.]
rng=1
samples=[]
for off in range(0,len(stream),8):
    voiced,pi,ei,ix=unpack(stream[off:off+8])
    pitch_u=max(1,min(255,round((50+(350/128)*pi)/12.5)))
    acc=0; centers=[]; prev=0
    for i,x in enumerate(ix[:6]):
        acc=min(255,acc+du(i,x))
        if i%2==0: prev=acc
        else: centers.append(min(255,prev+acc))
    vols=[energy[ei],max(0,energy[ei]-1),max(0,energy[ei]-2)]
    y=np.zeros(N,dtype=np.float64)
    if voiced:
        for ch in range(3):
            u=snap(centers[ch],pitch_u)
            f=u*12.5
            per=max(1,min(4095,round(AY/(16*f))))
            fq=AY/(16*per)
            t=np.arange(N)
            ph=phase[ch]+2*np.pi*fq*t/FS
            y += (vols[ch]/15.0)*np.sign(np.sin(ph))
            phase[ch]=(ph[-1]+2*np.pi*fq/FS)%(2*np.pi)
        y/=3.0
    else:
        # deterministic pseudo-noise; amplitude ratios match assembly roughly
        v0=energy[ei]; vs=[v0,max(0,v0-2),max(0,v0-4)]
        amp=sum(vs)/(45.0)
        n=np.empty(N)
        for j in range(N):
            # simple 16-bit LFSR approximation; enough for an audible preview
            bit=((rng>>0)^(rng>>2)^(rng>>3)^(rng>>5))&1
            rng=(rng>>1)|(bit<<15)
            n[j]=1.0 if (rng&1) else -1.0
        y=n*amp
    samples.append(np.clip(y,-1,1))
y=np.concatenate(samples)
write(HERE/'zx_ay_preview.wav',FS,np.int16(y*28000))
print('wrote reference_codec2.wav and zx_ay_preview.wav',len(y)/FS,'s')
