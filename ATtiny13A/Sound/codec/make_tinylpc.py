"""Experimental 6-pole 5-byte/frame LPC parameters for ATtiny13A.
Not wire compatible with LPC1/LPC2: this is the microcontroller-limited codec.
"""
from scipy.io import wavfile
from scipy.signal import resample_poly, lfilter
import numpy as np
from pathlib import Path
HERE=Path(__file__).parent
sr0,y=wavfile.read(HERE/'tts_source.wav')
sr=7500
x=resample_poly(y.astype(float)/32768.,50,147)
x*=.9/max(np.max(abs(x)),1e-5)
H=256; N=320
ORDER=6
pre=np.r_[x[0],x[1:]-.65*x[:-1]]

def levinson(a):
    R=np.array([np.dot(a[k:],a[:len(a)-k]) for k in range(ORDER+1)])
    R[0]*=1.008
    ks=[]; aa=[1.];err=R[0]
    for m in range(1,ORDER+1):
        k=np.clip(-(R[m]+sum(aa[j]*R[m-j] for j in range(1,m)))/max(err,1e-10),-.875,.875)
        bb=aa+[0]
        for j in range(1,m): bb[j]=aa[j]+k*aa[m-j]
        bb[m]=k;aa=bb;ks.append(k);err*=max(0.01,1-k*k)
    return np.array(ks),np.sqrt(max(0,err/N))

def pitchtrack(st):
    seg=x[max(0,st-80):min(len(x),st+H+80)]
    if len(seg)<180: return 0,0
    y=seg-seg.mean();peak=np.max(abs(y))
    if peak<.001:return 0,0
    y=np.sign(y)*np.maximum(0,np.abs(y)-peak*.27)
    lo,hi=round(sr/260),round(sr/60)
    vals=[]
    for lag in range(lo,hi+1):
        a=y[lag:];b=y[:-lag]; c=a.dot(b)/np.sqrt(a.dot(a)*b.dot(b)+1e-8)
        vals.append((c,lag))
    return max(vals)

frames=[];qualities=[]
for st in range(0,len(x),H):
    seg=pre[max(0,st-32):min(len(pre),st-32+N)]
    win=np.hamming(N);buf=np.zeros(N);buf[:len(seg)]=seg
    buf=(buf-buf.mean())*win
    ks,err=levinson(buf)
    corr,per=pitchtrack(st)
    voiced=corr>.40 and err>.0015
    # Noisy / unvoiced segments need more instantaneous energy than pulses.
    amp=np.sqrt(np.mean(x[st:min(len(x),st+H)]**2))
    energy=int(np.clip(round(amp*110),0,15))
    if amp < .002: energy=0
    # for strongly voiced, the excitation is single short impulse per pitch period
    if voiced and energy>0: energy=min(15,max(1,int(round(amp*180))))
    # voiced periods fits in uint8
    pitch=per if voiced and energy>0 else 0
    q=np.clip(np.rint(ks*8),-7,7).astype(int)
    frames.append((pitch,energy,*q))
    qualities.append((st/sr,amp,err,corr,ks,q))
print('Frame count:',len(frames),'samples:',len(x),'duration:',len(x)/sr,'Flash voice bytes:',len(frames)*5)
print('Energy distributions:', sorted(set(f[1] for f in frames)),'voiced frames:',sum(f[0]!=0 for f in frames))

buf=bytearray()
for pitch,energy,k0,k1,k2,k3,k4,k5 in frames:
    buf.extend([pitch,(energy&15) | ((k0+8)<<4), (k1+8)|((k2+8)<<4), (k3+8)|((k4+8)<<4), (k5+8)])
# Last byte's high nibble unused; could use for gain more, presently just 0
(HERE/'voice_tinylpc.bin').write_bytes(buf)

# Approximate hardware's fixed point lattice synthesis, wrapping arithmetic on registers.
state=[0]*(ORDER+1);seed=0xa7;pcnt=1;out=[];k=[0]*4;gain=0;pitch=0;maxabs=0;clips=0
for n in range(len(frames)*H):
    if n%H==0:
        pitch,gain,*k=frames[n//H]
    if pitch:
        pcnt-=1
        if pcnt==0: pcnt=pitch;src=2*gain
        else: src=0
    else:
        seed=(seed>>1) ^ (0xb8 if seed&1 else 0)
        src=-gain if seed&1 else gain
    v=src
    for m in range(ORDER,0,-1):
        val=int(np.floor(k[m-1]*state[m-1]/8))
        v=v-val
        if v>127 or v<-128: clips+=1
        v=(v+128)%256-128
        val=int(np.floor(k[m-1]*v/8))
        st=state[m-1]+val
        state[m]=(st+128)%256-128
    state[0]=v
    out.append(v)
    maxabs=max(maxabs,abs(v))
yout=np.array(out,dtype='float64')
print('Tiny 8bit:', 'RMS=',np.sqrt(np.mean(yout*yout)),'maxabs=',maxabs,'clip events=',clips)
import wave
with wave.open(str(HERE/'voice_tinylpc_preview.wav'),'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
    samples=np.clip(yout*256,-32768,32767).astype('<i2')
    w.writeframes(samples.tobytes())
