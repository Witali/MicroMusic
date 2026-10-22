#!/usr/bin/env python3
"""Deterministic analysis-by-synthesis optimization of ATtiny13 MiniLPC-HQ4.

Inputs: proven HQ3 speech data and original 7500 Hz WAV, not guessed params.
Candidate operations: pitch/gain/mode, reflection coefficients, joint edits,
frame boundary displacement, frame subdivision, half-formant transition.
Every candidate is synthesized by the same integer model used for AVR and
rated by STOI and log spectrum with hard Flash and click constraints.
Outputs: exact frames+durations checkpoint NPZ, JSON trace, new speech.hq.
No new format and no legacy decode path are added to MCU.
"""
from pathlib import Path
import argparse,json,time,os
import numpy as np,soundfile as sf
from codec import decode_stream,encode_stream,src_size
from model import decode
from quality import Compare
ROOT=Path(__file__).resolve().parent


def coeff_update(f,frame,coeff,delta):
    col=2+coeff//2;v=int(f[frame,col]); shift=(coeff%2)*4
    q=(v>>shift)&15; qq=int(np.clip(q+delta,0,15))
    f[frame,col]=(v&~(15<<shift))|(qq<<shift)


def modify(rng,f,d):
    n=len(f); i=int(rng.integers(0,n)); op=int(rng.integers(0,12))
    g=f.copy();dd=d.copy(); j=min(n-1,i+1)
    if op in (0,1): # voiced pitch: octave confusions, or small frequency changes
        p=int(f[i,0]); choices = list(range(-5,6)) if op==0 else [0,p//2-p,2*p-p,p*3//2-p, int(f[max(0,i-1),0])-p,int(f[min(n-1,i+1),0])-p]
        step=int(rng.choice(choices))
        if p==0: return None
        new=p+step
        if not 12<=new<=126 or new==p:return None
        g[i,0]=new
    elif op==2: # gain
        v=int(f[i,1]);gain=(v&15);step=int(rng.choice([-5,-3,-2,-1,1,2,3,5]))
        g[i,1]=(v&48)|int(np.clip(gain+step,0,15))
    elif op==3: # excitation impulse profile
        v=int(f[i,1]);mode=int(rng.integers(0,4))
        if v>>4==mode:return None
        g[i,1]=(v&15)|(mode<<4)
    elif op==4: # spectral coefficient local
        coef=int(rng.integers(0,8));coeff_update(g,i,coef,int(rng.choice([-3,-2,-1,1,2,3])))
    elif op==5: # paired spectral perturbation
        if j==i:return None
        coef=int(rng.integers(0,8));step=int(rng.choice([-2,-1,1,2]));coeff_update(g,i,coef,step);coeff_update(g,j,coef,step)
    elif op==6: # paired pitch and gain slope
        if f[i,0]==0:return None
        pstep=int(rng.choice([-4,-2,-1,1,2,4]));gstep=int(rng.choice([-2,-1,1,2]));p=int(f[i,0])+pstep
        if not 12<=p<=126:return None
        g[i,0]=p;v=int(f[i,1]);g[i,1]=(v&48)|int(np.clip((v&15)+gstep,0,15))
    elif op==7: # share other frame's local spectral structure
        if j==i:return None
        half=int(rng.integers(0,2))
        for k in (half*4,half*4+1,half*4+2,half*4+3):
            cv=(int(g[i,2+k//2])>>(4*(k%2)))&15
            nv=(int(g[j,2+k//2])>>(4*(k%2)))&15
            if cv!=nv:coeff_update(g,i,k,int(np.sign(nv-cv)))
    elif op==8: # +/-64 boundaries
        if j==i:return None
        shift=int(rng.choice([-64,64]))
        if int(dd[i])+shift not in (64,128,192,256) or int(dd[j])-shift not in (64,128,192,256):return None
        dd[i]=int(dd[i])+shift;dd[j]=int(dd[j])-shift
    elif op==9: # add a short subframe for rapid consonant transitions
        length=int(dd[i]);
        if length<128:return None
        piece=int(rng.choice([64,128,192]));tail=length-piece
        if piece not in (64,128,192,256) or tail not in (64,128,192,256):return None
        g=np.insert(g,i+1,g[i].copy(),axis=0).astype(np.uint8)
        dd=np.insert(dd,i+1,tail).astype(np.uint16);dd[i]=piece
        direction=int(rng.integers(0,3))
        if direction==0 and g[i+1,0]:g[i+1,0]=int(np.clip(int(g[i+1,0])+int(rng.choice([-3,-2,-1,1,2,3])),12,126))
        elif direction==1:
            k=int(rng.integers(8));coeff_update(g,i+1,k,int(rng.choice([-2,-1,1,2])))
        else:
            v=int(g[i+1,1]);g[i+1,1]=(v&48)|int(np.clip((v&15)+int(rng.choice([-2,-1,1,2])),0,15))
    elif op==10: # change spectral transitions on attack, 2-3 frames
        coeff=int(rng.integers(8));step=int(rng.choice([-2,-1,1,2]))
        for k in range(i,min(i+int(rng.integers(2,4)),n)):coeff_update(g,k,coeff,step)
    elif op==11: # remove redundant short frame and merge durations
        if j==i:return None
        length=int(dd[i])+int(dd[j]);
        if length not in (64,128,192,256):return None
        if rng.random()<0.5:g=np.delete(g,i+1,axis=0)
        else:g=np.delete(g,i,axis=0)
        dd=np.delete(dd,j);dd[i]=length
    else:return None
    if g.shape[0] and np.array_equal(g,f) and np.array_equal(dd,d):return None
    return g,dd,op


def run(name,seconds=60,seed=513,limit=1024,checkpoint_every=15):
    init=ROOT/'inputs'/name
    dest=ROOT/'results'/name
    dest.mkdir(parents=True,exist_ok=True)
    f,d=decode_stream((init/'speech.hq').read_bytes())
    assert encode_stream(f,d,False)==(init/'speech.hq').read_bytes()
    if (dest/'trained.npz').exists():
        checkpoint=np.load(dest/'trained.npz');f=checkpoint['frames'].copy();d=checkpoint['durations'].copy()
    old_output=decode(f,d,0)
    ref,sr=sf.read(init/'original.wav');assert sr==7500
    comp=Compare(ref)
    code_size=src_size(init/'firmware.S')
    def evaluate(fr,dur):
        raw=encode_stream(fr,dur)
        if len(raw)+code_size>limit:return None
        result=decode(fr,dur,0)
        st,sp,clicks=comp.scores(result)
        if clicks>0:return None
        return (float(st),float(sp),len(raw),result)
    initial=evaluate(f,d)
    if initial is None:raise RuntimeError('baseline exceeds budget or click limit')
    best=initial;start=initial
    rng=np.random.default_rng(seed)
    accepted=0;trials=0;freq={}
    t0=time.monotonic();last_report=t0
    def objective(m):
        return m[0]-0.002*max(0,m[1]-start[1])-0.0002*m[1]
    score=objective(best)
    trace=[]
    # persist bit-perfect model and clear provenance
    def save():
        stream=encode_stream(f,d)
        np.savez_compressed(dest/'trained.npz',frames=f,durations=d)
        (dest/'speech.hq').write_bytes(stream[:-1])
        (dest/'optimizer.json').write_text(json.dumps({
          'name':name,'seed':seed,'seconds':seconds,'executed_seconds':round(time.monotonic()-t0,2),
          'base_stoi':start[0],'base_spectral_error':start[1], 'new_stoi':best[0],
          'new_spectral_error':best[1],'code_bytes':code_size,'speech_bytes':best[2],
          'flash_bytes':code_size+best[2],'clicks_48':0,
          'trials':trials,'accepted':accepted,'operations':freq,'history':trace
        },ensure_ascii=False,indent=2))
    while time.monotonic()-t0<seconds:
        candidate=modify(rng,f,d)
        if candidate is None:continue
        ff,dd,op=candidate
        m=evaluate(ff,dd)
        trials+=1
        if m is None:continue
        s=objective(m)
        # no measurable loss of STOI; spectral variation controlled
        if m[0]+.00002>=best[0] and m[1]<start[1]+0.10 and s>score+0.000001:
            f,d=ff,dd;best=m;score=s;accepted+=1
            freq[op]=freq.get(op,0)+1
            trace.append({'trial':trials,'stoi':round(m[0],7),'spec':round(m[1],5),'bytes':m[2],'operation':op})
            if accepted%checkpoint_every==0:save()
        if time.monotonic()-last_report>14:
            print(name,'trial',trials,'accepted',accepted,'STOI',round(best[0],7),'spec',round(best[1],5),'bytes',best[2],'seconds',round(time.monotonic()-t0),flush=True)
            last_report=time.monotonic()
    save()
    print(name,'FINAL',round(best[0],7),'base',round(start[0],7),'spec',round(best[1],5),'speech',best[2],'FLASH',code_size+best[2],'trials',trials,'accepted',accepted,flush=True)
    return best

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--voice',choices=['chego','otvechaesh','vinni'],default='chego');p.add_argument('--seconds',type=float,default=60);p.add_argument('--seed',type=int,default=513);p.add_argument('--budget',type=int,default=1024)
    a=p.parse_args();run(a.voice,a.seconds,a.seed,a.budget)
