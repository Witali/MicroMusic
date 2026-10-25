#!/usr/bin/env python3
"""Host-side research on Codec2 3200 Tiny13-style resonators.
Comparing to the reference Codec2 PCM is an *imperfect proxy*, not subjective quality.
The final tested MCU algorithm lives in src/*.S; these are offline experiments.
"""
from pathlib import Path
import sys
import numpy as np, soundfile as sf
from numba import njit
from pystoi import stoi
from scipy.signal import stft
from codec2_test_common import fields
ROOT=Path(__file__).resolve().parents[1]
R1=Path('/mnt/data/Codec2_Tiny13_Resonator_R1/audio')
PITCH=lambda p:410+22*p+(p>>2)+(p>>3)
A=np.array([fields(x) for x in []]) if False else None

def prepared(filename):
    b=(ROOT/'tests'/filename).read_bytes()
    ar=np.zeros((len(b)//8,15),dtype=np.int16)
    for i in range(len(ar)):
        v0,v1,p,e,ls=fields(b[i*8:(i+1)*8]);ar[i]=[v0,v1,p,e,*ls,0]
    return ar

@njit
def decode(arr,nb_res,qshift,gain_mode,noise_div,leak_shift,smooth,tone_weight,highpass,noise_floor,coeff_table):
    y=np.zeros(5,np.int16); v=np.zeros(5,np.int16);coeff=np.zeros(5,np.int16)
    phase=0; noise=0xa5;prev_raw=0;hp_state=0; prev_noise=0
    samples=np.zeros(len(arr)*160,np.int16)
    # count internal state wrap to reveal quality bugs
    overflows=0
    for t in range(len(arr)):
        fr=arr[t];v0,v1,p,e=int(fr[0]),int(fr[1]),int(fr[2]),int(fr[3]);inc=410+22*p+(p>>2)+(p>>3)
        centers=np.zeros(5,np.int16)
        pos=0
        for j in range(10):
            val=int(fr[j+4]);diff=val+1 if (j<3 or j>=6 or val<8) else 2*val-6
            pos+=diff
            if j%2==0:oldpos=pos
            else:centers[j//2]=min(35,((oldpos+pos)>>1)>>2)
        target=np.zeros(5,np.int16)
        for k in range(5):target[k]=coeff_table[centers[k]]
        if not smooth:
            for k in range(nb_res):coeff[k]=target[k]
        if gain_mode==0:
            gainv=(e>>2)+1;gainn=(e>>3)+1
        elif gain_mode==1:
            gainv=(e>>2)+1 if e>0 else 0
            gainn=(e>>3)+1 if e>0 else 0
        else:
            if e<2:gainv=0
            else:gainv=max(1,min(18,int(np.floor(1.5*2.0**((e-16)/4.0)+0.5))))
            gainn=0 if e<5 else max(1,min(6,(gainv+2)//4))
        for n in range(160):
            if smooth and (n&7)==0:
                for k in range(nb_res):
                    d=int(target[k])-int(coeff[k]);coeff[k]+=min(1,max(-1,d))
            voice=v0 if n<80 else v1
            phase+=inc
            pulse=phase>65535
            phase&=65535
            if voice:
                excite=gainv if pulse else 0
            else:
                x=noise
                x^=(x<<3)&255;x^=x>>5;x^=(x<<1)&255;noise=x&255
                excite=-gainn if noise&128 else gainn
            out=0
            for j in range(nb_res):
                a=int(coeff[j]);oj=int(y[j]);ov=int(v[j]);
                # emulate signed rounding of fixed Q5 or Q4
                m=a*oj;prod=(m>>qshift) if m>=0 else -((-m)>>qshift)
                newv=(ov-prod+128)&255;newv-=128
                leak= (newv+15)>>4 if newv>0 else newv>>4
                if leak_shift==3:leak=(newv+7)>>3 if newv>0 else newv>>3
                if leak_shift==5:leak=(newv+31)>>5 if newv>0 else newv>>5
                nu=newv-leak+excite
                if nu>127 or nu<-128:overflows+=1
                newv=((nu+128)&255)-128
                m=a*newv;prod=(m>>qshift) if m>=0 else -((-m)>>qshift)
                ny=oj+prod
                if ny>127 or ny<-128:overflows+=1
                ny=((ny+128)&255)-128
                y[j]=ny;v[j]=newv
                if tone_weight==0:out+=ny
                elif tone_weight==1:out+=ny if j<3 else ny//2
                elif tone_weight==2:out+=ny if j==0 else ny//2
            if highpass:
                if voice==0:
                    out+=((excite-prev_noise)<<highpass)
                    prev_noise=excite
            out=((out+128)&255)-128
            out=min(63,max(-64,out))
            sample=(out<<1)
            if noise_floor:
                hp_state+=sample-(hp_state>>5)
                sample-=hp_state>>5
            samples[t*160+n]=sample
    return samples,overflows


def metric(ref,x):
    xs=x.astype(float)/128
    freqs,tt,a=stft(ref,8000,nperseg=256,noverlap=128)
    _,_,b=stft(xs,8000,nperseg=256,noverlap=128)
    a=np.abs(a);b=np.abs(b)
    d=np.log(a+3e-4)-np.log(b+3e-4)
    logerr=float(np.mean(abs(d))*8.6858896)
    c=np.mean(np.sum(a*b,axis=0)/(np.linalg.norm(a,axis=0)*np.linalg.norm(b,axis=0)+1e-9))
    return (round(stoi(ref,xs,8000),4),round(logerr,2),round(c,4),round(float(np.std(xs)),4))

def run():
    DATA=[('speech.c2zx',sf.read(R1/'english_codec2_reference.wav')[0]),('codec2_3200_8byte_frames.bin',sf.read(R1/'russian_codec2_reference.wav')[0])]
    arr=[prepared(s) for s,_ in DATA]
    tests={
        'baseline_Q7':(3,7,0,2,4,0,0,0,0),
        'Q5_small':(3,5,0,2,4,0,0,0,0),
        'Q4_small':(3,4,0,2,4,0,0,0,0),
        'Q5_silence':(3,5,1,2,4,0,0,0,0),
        'Q5_logEnergy':(3,5,2,2,4,0,0,0,0),
        'Q5_leak3':(3,5,2,2,3,0,0,0,0),
        'Q5_leak5':(3,5,2,2,5,0,0,0,0),
        'Q5_log_smooth':(3,5,2,2,4,1,0,0,0),
        'Q5_log_hp':(3,5,2,2,4,1,0,0,1),
        'Q4_4formants':(4,4,2,2,4,1,1,0,0),
        'Q5_4formants':(4,5,2,2,4,1,1,0,0),
        'Q5_log_bypass':(3,5,2,2,4,1,0,1,0),
        'Q5_log_bypass2':(3,5,2,2,4,1,0,2,0),
    }
    for key,opt in tests.items():
        n,q,g,ndamp,leak,smooth,weight,hp,nfloor=opt
        tbl=np.array([min((1<<q)*2-2,int(np.floor((2*(1<<q)*np.sin(np.pi*100*i/8000))+0.5))) for i in range(36)],dtype=np.int16)
        # original 31-entry R1 table used 256 sin(pi f /fs), q=7
        if q==7:tbl=np.array([min(250,round(256*np.sin(np.pi*100*i/8000))) for i in range(36)],dtype=np.int16)
        total=[];overflow=0
        for (stem,ref),f in zip(DATA,arr):
            x,wrap=decode(f,n,q,g,ndamp,leak,smooth,weight,hp,nfloor,tbl)
            total.append(metric(ref,x));overflow+=wrap
        print(key,opt,'EN',total[0],'RU',total[1],'overflow',overflow,flush=True)
if __name__=='__main__':run()
