#!/usr/bin/env python3
"""LPC2 v3 experiment: closed-loop waveform-preserving excitation coding.

LPX3 contains a legacy LPC2 v2 bitstream (LSF/formants, F0/modes), followed by
blockwise quantised excitation. This is intentionally a *higher bit-rate* profile
of LPC2, NOT an ATtiny13 firmware codec. A tiny decoder must remain separate.

No target waveform or floats are embedded: encoded excitation is stored at
2/3/4 bits per 8 kHz sample plus an 8-bit scale for each 10ms block.
"""
from __future__ import annotations
import os, sys, json, math, struct, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, stft
from numba import njit

ROOT=Path(__file__).resolve().parent
JS_CODEC=ROOT/'lpc2_v2_reference.html'
HEADER=struct.Struct('<4sBBHIIHHI')  # magic, ver, bits, Fs, nsamples, baseLen, blockSize, reserved, nBlocks

JS_COEFFS='''async ({base}) => {
 const raw=Uint8Array.from(base).buffer, d=unpackLPC2(raw), m=d.meta, F=d.frames;
 const lsf=F.map(decodeLpc2FrameLsf), coeffs=[];
 let prev=lsf[0]||defaultLsf(10);
 for(let fi=0;fi<F.length;fi++){
  const cur=lsf[fi];
  for(let sub=0;sub<8;sub++){
   let t=(sub+.5)/8;
   const a=lsfToLpc(stabilizeLsf(cur.map((v,i)=>prev[i]+(v-prev[i])*t),10));
   const start=fi*m.H+Math.floor(sub*m.H/8),end=fi*m.H+Math.floor((sub+1)*m.H/8);
   coeffs.push([start,end,Array.from(a).slice(1)]);
  }
  prev=cur;
 }
 return {pre:m.pre, sr:m.sr, ns:m.samples, coeffs};
}'''

def coeffs_from_lpc2(base:bytes):
    from playwright.sync_api import sync_playwright
    html=JS_CODEC.read_text(encoding='utf-8')
    with sync_playwright() as p:
        br=p.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg=br.new_page(); pg.set_content(html,wait_until='load')
        data=pg.evaluate(JS_COEFFS,{'base':list(base)})
        br.close()
    co=np.zeros((int(data['ns']),10), dtype=np.float64)
    for st,en,a in data['coeffs']:
        co[st:min(en,len(co)),:]=a
    return float(data['pre']),int(data['sr']),co

@njit(cache=True)
def encode_block_pre(target, coeffs, hist, scale, bits):
    half=1<<(bits-1)
    out=np.zeros(len(target),np.uint8)
    err=0.0
    for i in range(len(target)):
        az=0.0
        for k in range(10):az+=coeffs[i,k]*hist[k]
        needed=target[i]+az
        q=int(np.floor(needed/scale+.5))
        if q<-half:q=-half
        if q>half-1:q=half-1
        y=q*scale-az
        if y>2:y=2
        if y<-2:y=-2
        d=target[i]-y
        err+=d*d
        for k in range(9,0,-1):hist[k]=hist[k-1]
        hist[0]=y
        out[i]=q+half
    return out,err

@njit(cache=True)
def decode_qs(q,scale,hist,co,bits):
    out=np.empty(len(q),np.float64)
    half=1<<(bits-1)
    for j in range(len(q)):
        az=0.0
        for k in range(10):az+=co[j,k]*hist[k]
        y=(int(q[j])-half)*scale-az
        if y>2:y=2
        if y< -2:y=-2
        for k in range(9,0,-1):hist[k]=hist[k-1]
        hist[0]=y
        out[j]=y
    return out

def scale_to_byte(scale):
    return int(np.clip(np.round((np.log2(max(1e-9,float(scale))/0.001))*16+128),0,255))
def byte_to_scale(b): return float(0.001*2**((int(b)-128)/16))

def pack_codes(q,bits):
    accum=0;n=0;out=bytearray()
    for v in q:
        accum|=int(v)<<n;n+=bits
        while n>=8:
            out.append(accum&255);accum>>=8;n-=8
    if n:out.append(accum&255)
    return bytes(out)

def unpack_codes(raw,bits,count):
    a=np.zeros(count,np.uint8);mask=(1<<bits)-1;accum=0;n=0;i=0
    for b in raw:
        accum|=b<<n;n+=8
        while n>=bits and i<count:
            a[i]=accum&mask;i+=1;accum>>=bits;n-=bits
    if i!=count:raise ValueError('truncated excitation')
    return a

def spectral_shape_distance(ref, candidate, sr):
    n=min(len(ref),len(candidate));ref=ref[:n];candidate=candidate[:n]
    f,t,R=stft(ref,sr,nperseg=256,noverlap=192)
    _,_,X=stft(candidate,sr,nperseg=256,noverlap=192)
    bands=np.geomspace(110,sr*.48,20)
    a=[];b=[]
    for lo,hi in zip(bands[:-1],bands[1:]):
        sel=(f>=lo)&(f<hi)
        if sel.any():
            a.append(np.mean(np.abs(R[sel]),axis=0))
            b.append(np.mean(np.abs(X[sel]),axis=0))
    A=np.log(np.maximum(np.array(a),1e-6))
    B=np.log(np.maximum(np.array(b),1e-6))
    A-=A.mean(axis=0);B-=B.mean(axis=0)
    w=np.sqrt(np.maximum(0,np.mean(np.abs(R),axis=0))); w/=w.sum()+1e-9
    return float(np.sum(w*np.mean(abs(A-B),axis=0)))

def apply_brightness(x,alpha):
    y=np.asarray(x, np.float64).copy()
    y[1:]-=alpha*x[:-1]
    return y

def encode_lpx3(original, sr, base:bytes, bits:int, block_size=80, cache=None,auto_brightness=True):
    assert bits in (2,3,4)
    if cache is None: pre, fs, coeffs=coeffs_from_lpc2(base)
    else: pre, fs, coeffs=cache
    assert sr==fs and len(original)==len(coeffs),(sr,fs,len(original),len(coeffs))
    xx=np.asarray(original,np.float64)
    xp=xx.copy();xp[1:]-=pre*xx[:-1]
    n=len(xp);hist=np.zeros(10,np.float64); codes=np.zeros(n,np.uint8)
    scales=bytearray();blocks=[];total=0.0
    for st in range(0,n,block_size):
        en=min(st+block_size,n)
        target=xp[st:en];co=coeffs[st:en]
        # Initial variance of true (unquantised) excitation, not of direct waveform.
        energy=np.empty(len(target),np.float64)
        for j in range(len(target)):
            lag=st+j
            az=sum(co[j,k]*xp[lag-k-1] for k in range(10) if lag-k-1>=0)
            energy[j]=target[j]+az
        rms=max(0.00005,float(np.sqrt(np.mean(energy**2))))
        # Search scale with analysis-by-synthesis of the actual quantized excitation.
        nominal=rms/max(1,(1<<(bits-1))-0.5)
        trial=[nominal*t for t in [0.45,0.6,0.75,0.9,1,1.12,1.3,1.55,1.85,2.25,2.9]]
        best=(1e99,None,None)
        for s in trial:
            sb=scale_to_byte(s);step=byte_to_scale(sb)
            qq,loss=encode_block_pre(target,co,hist.copy(),step,bits)
            if loss<best[0]:best=(loss,sb,qq)
        loss,code,qq=best
        scales.append(code);codes[st:en]=qq
        _,actual=encode_block_pre(target,co,hist,byte_to_scale(code),bits)
        total+=actual
        blocks.append(float(loss/len(target)))
    qdata=pack_codes(codes,bits)
    hd=HEADER.pack(b'LPX3',1,bits,sr,n,len(base),block_size,0,len(scales))
    container=hd+base+bytes(scales)+qdata
    initial=decode_lpx3(container,cache=cache)[0]
    # Choose the one-byte brightness (encoded in a reserved 16-bit field)
    # by minimizing the framewise timbral/spectral mismatch with the source.
    # No gender-based rules or manually chosen voiced profiles are used.
    alpha=0.0
    if auto_brightness:
        score=1e30
        for trial in np.linspace(0,.70,15):
            y=apply_brightness(initial,trial)
            v=spectral_shape_distance(original,y,sr)
            if v<score:score=v;alpha=float(trial)
    hd=HEADER.pack(b'LPX3',1,bits,sr,n,len(base),block_size,round(alpha*1000),len(scales))
    container=hd+base+bytes(scales)+qdata
    output=decode_lpx3(container,cache=cache)[0]
    info={'bits':bits,'bytes':len(container),'duration':n/sr,'bitrate_kbps':round(len(container)*8/n*sr/1000,2),'mse_pre':total/n,'blocks':len(scales),'base_bytes':len(base),'brightness':round(alpha,3)}
    return container,output,info

def decode_lpx3(data:bytes,cache=None):
    if len(data)<HEADER.size:raise ValueError('short LPX3 header')
    magic,version,bits,sr,n,baselen,blocksize,reserved,nblocks=HEADER.unpack_from(data)
    if magic!=b'LPX3' or version!=1 or bits not in [2,3,4] or reserved>700:raise ValueError('invalid LPX3 v1 file')
    if not (sr>=4000 and sr<=96000 and n<=sr*60*60 and 20<=blocksize<=2048):raise ValueError('implausible header')
    end=HEADER.size+baselen+nblocks
    if end>len(data) or nblocks!=(n+blocksize-1)//blocksize:raise ValueError('bad LPX3 block count')
    base=data[HEADER.size:HEADER.size+baselen];scales=data[HEADER.size+baselen:end]
    q=unpack_codes(data[end:],bits,n)
    if cache is None:pre,fs,coeffs=coeffs_from_lpc2(base)
    else:pre,fs,coeffs=cache
    if fs!=sr or len(coeffs)!=n:raise ValueError('LPC2 descriptor mismatch')
    hist=np.zeros(10,np.float64);yy=np.zeros(n,np.float64)
    for block,st in enumerate(range(0,n,blocksize)):
        en=min(st+blocksize,n)
        yy[st:en]=decode_qs(q[st:en],byte_to_scale(scales[block]),hist,coeffs[st:en],bits)
    out=np.empty(n,np.float64);last=0
    for i in range(n):
        v=yy[i]+pre*last
        out[i]=np.clip(v,-1.0,1.0);last=np.clip(v,-2,2)
    if reserved:
        out=apply_brightness(out,reserved/1000)
    out=np.clip(out,-1.0,1.0)
    return out.astype('float32'),{'sr':sr,'bits':bits,'samples':n,'base_bytes':baselen,'total_bytes':len(data),'block_samples':blocksize,'brightness':reserved/1000}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('input',help='source WAV 8 kHz or LPX3')
    p.add_argument('--base',help='corresponding LPC2 Voice v2 .lp2 (for encoding)')
    p.add_argument('--bits',type=int,choices=[2,3,4],default=3)
    p.add_argument('--out',default=None)
    args=p.parse_args()
    path=Path(args.input)
    if path.suffix.lower()=='.lpx3':
        out,m=decode_lpx3(path.read_bytes()); dest=Path(args.out or path.with_suffix('.wav'));sf.write(dest,out,m['sr']);print(dest,m)
    else:
        if not args.base:p.error('--base is required to encode')
        sig,sr=sf.read(path);assert sig.ndim==1
        raw,y,m=encode_lpx3(sig,sr,Path(args.base).read_bytes(),args.bits)
        dest=Path(args.out or path.with_suffix('.lpx3'));dest.write_bytes(raw);sf.write(dest.with_suffix('.wav'),y,sr)
        print(dest,m)
