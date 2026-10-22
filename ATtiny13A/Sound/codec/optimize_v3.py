"""TinyLPC model-matched speech encoder. CPU code is still actual AVR assembly.
One frame: 256 samples at 7500Hz, 5 bytes with 7 4-bit reflection coeffs.
Tests, objective scores are tied to user's ORIGINAL uploaded audio, not TTS.
"""
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import stft, butter, sosfiltfilt, resample_poly
from numba import njit
from analyze import x,FS,H,ORDER,levinson,get_pitch,P
from pystoi import stoi

@njit(cache=True)
def simulate(K,pitches,energies,length):
    state=np.zeros(7,dtype=np.int64)
    seed=0xa7; count=1; y=np.zeros(len(pitches)*256,dtype=np.float64)
    for t in range(len(y)):
        fi=t//256; k=K[fi]
        pp=pitches[fi];amp=energies[fi]
        if pp:
            count=(count-1)&255
            if count==0:
                count=pp
                excitation=amp*5
            else:
                dt=(pp-count)&255
                if dt==1:excitation=amp*3
                elif dt==3:excitation=-amp*2
                else:excitation=0
        else:
            seed=(seed>>1)^(0xb8 if (seed&1) else 0)
            excitation=-amp if (seed&1) else amp
        v=excitation
        for stage in range(6,-1,-1):
            w=(k[stage]*state[stage])>>3
            v=((v-w+128)&255)-128
            if stage>0:
                w2=(k[stage]*v)>>3
                state[stage]=((state[stage-1]+w2+128)&255)-128
        state[0]=v
        y[t]=v/128
    return y[:length]

N=int(np.ceil(len(x)/H));xn=np.pad(x,(0,N*H-len(x)))
Kbase=[];rms=[];corrs=[];lags=[];errs=[]
for fi in range(N):
    t=fi*H
    seg=xn[t:t+H]
    k,err=levinson(seg)
    Kbase.append(np.clip(np.rint(k*8),-7,7).astype(np.int64))
    rms.append(float(np.sqrt((seg*seg).mean())))
    co,lag=get_pitch(t)
    corrs.append(co);lags.append(lag);errs.append(err)
Kbase=np.asarray(Kbase,dtype=np.int64);rms=np.asarray(rms);corrs=np.asarray(corrs);lags=np.asarray(lags,dtype=np.int64);errs=np.asarray(errs)

def lsd(y, orig=x):
    # weighted normalized melish spectral distance; 256 FFT with 50% overlap
    orig=orig[:min(len(orig),len(y))];y=y[:len(orig)]
    f,t,a=stft(orig,FS,nperseg=256,noverlap=128);_,_,b=stft(y,FS,nperseg=256,noverlap=128)
    aa=np.maximum(np.abs(a),1e-5);bb=np.maximum(np.abs(b),1e-5)
    aa/=np.sqrt((aa**2).sum(axis=0,keepdims=True)); bb/=np.sqrt((bb**2).sum(axis=0,keepdims=True))
    logs=np.abs(20*np.log10(aa)-20*np.log10(bb))
    speech=(np.sqrt((np.abs(a)**2).sum(axis=0))>.009)
    frw=(np.clip(500/np.maximum(500,f),.2,1.0))**.1
    return float(np.mean(logs[:,speech]*frw[:,None]))


def metrics(y):
    src=x[:len(y)];y=y[:len(src)]
    if len(src)<100:return 0,0
    sc=stoi(src,y,FS)
    dist=lsd(y,src)
    return float(sc),float(dist)

if __name__=='__main__':
    print('frames',N,'voice bytes',N*5,'duration',len(x)/FS,flush=True)
    # initial jit
    _=simulate(Kbase,lags,np.zeros(N,dtype=np.int64),len(x))
    rows=[]
    for threshold in [.25,.32,.4,.5,.58,.65,.7,.75]:
     for ev in [45,60,75,90,110,140]:
      for en in [60,75,90,110,140]:
       pitch=np.where((corrs>threshold)&(rms>.01),lags,0).astype(np.int64)
       E=np.clip(np.rint(rms*np.where(pitch>0,ev,en)),0,15).astype(np.int64)
       E[rms<.005]=0;pitch[E==0]=0
       y=simulate(Kbase,pitch,E,len(x))
       s,d=metrics(y)
       rows.append((s,d,threshold,ev,en,pitch,E))
     print('threshold',threshold,'best',tuple(round(float(z),3) for z in max(rows,key=lambda t:t[0])[:5]),flush=True)
    rows.sort(key=lambda v:v[0],reverse=True)
    for r in rows[:15]:print('trial',tuple(round(float(z),4) for z in r[:5]),flush=True)
    best=rows[0];_,_,th,ev,en,pitch,energy=best
    from scipy.io import wavfile
    yy=simulate(Kbase,pitch,energy,len(x))
    np.clip(yy,-1,1)
    sf.write(P/'v3_initial_model.wav',yy,FS,subtype='PCM_16')
    np.savez(P/'v3_optimized.npz',K=Kbase,pitch=pitch,energy=energy,correlations=corrs)
    dat=bytearray()
    for i in range(N):
        kk=list(map(int,Kbase[i]));amp=int(energy[i]);pi=int(pitch[i]);
        dat.extend([pi,(amp&15)|((kk[0]+8)<<4),((kk[2]+8)<<4)|(kk[1]+8),((kk[4]+8)<<4)|(kk[3]+8),((kk[6]+8)<<4)|(kk[5]+8)])
    (P/'voice_tinylpc.bin').write_bytes(dat)
    print('ENCODED: ',len(dat),'bytes. metrics:',metrics(yy),flush=True)
