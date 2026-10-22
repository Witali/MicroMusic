#!/usr/bin/env python3
"""Closed-loop MiniLPC-HQ4 optimisation for three fixed utterances.

Runs on the EXACT eight-stage AVR integer LPC model; candidate frame streams are
packed using the native HQ3-only encoder. The metric compares against the
fixed, user-provided reference WAV. Deterministic given the seed and number
of trials (time limits disabled by default).

Usage: python optimize_hq4.py --phrase chego --max-trials 6000 --seed 1437

This is a research optimiser, not a universal automatic speech coder.
"""
import argparse,json,sys,time,shutil
from pathlib import Path
import numpy as np,soundfile as sf


from hq4_codec import unpack,encode
from model import decode
from quality import Compare
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'baseline'
SR=7500

def quant_edit(frames,i,k,delta):
    j=2+k//2;mask=15<<(4*(k%2)); q=(int(frames[i,j])>>(4*(k%2)))&15
    v=int(np.clip(q+delta,0,15));frames[i,j]=(int(frames[i,j])&~mask)|(v<<(4*(k%2)))

def pitch_edit(f,i,step):
    p=int(f[i,0]); npitch=p+step
    if p==0 or not 16<=npitch<=126: return False
    f[i,0]=npitch;return True

def evaluate(comp,ff,dd,budget,base_spec,max_clicks=0):
    data=encode(ff,dd)
    if len(data)>budget:return None
    signal=decode(ff,dd)
    # Most proposals are invalid because sudden jumps in the PWM stream.
    if np.max(np.abs(np.diff(signal.astype(np.int16)))) >= 48 and max_clicks==0:return None
    st,spec,clicks=comp.scores(signal)
    if clicks>max_clicks or spec>base_spec+0.035:return None
    return (st - 0.005*(spec-base_spec), st, spec, len(data), clicks)

def candidate(f,d,rng):
    ff=f.copy();dd=d.copy();n=len(f)
    i=int(rng.integers(n));op=int(rng.choice(10,p=[.28,.16,.10,.15,.06,.05,.05,.05,.05,.05]));
    if op==0:quant_edit(ff,i,int(rng.integers(8)),int(rng.choice([-2,-1,1,2])))
    elif op==1:
        g=int(ff[i,1])&15;step=int(rng.choice([-3,-2,-1,1,2,3]));ng=g+step
        if not 0<=ng<=15:return None
        ff[i,1]=(int(ff[i,1])&240)|ng
    elif op==2:ff[i,1]=(int(ff[i,1])&15)|(int(rng.integers(4))<<4)
    elif op==3:
        p=int(ff[i,0]);v=int(rng.choice([-5,-3,-2,-1,1,2,3,5]));
        if not pitch_edit(ff,i,v):return None
    elif op==4:
        k=int(rng.integers(8));v=int(rng.choice([-1,1]));
        for j in range(i,min(i+3,n)):quant_edit(ff,j,k,v)
    elif op==5:
        v=int(rng.choice([-2,-1,1,2]));
        for j in range(i,min(i+3,n)):
            if int(ff[j,0]):pitch_edit(ff,j,v)
    elif op==6:
        v=int(rng.choice([-1,1]));
        for j in range(i,min(i+3,n)):
            g=int(ff[j,1])&15;ff[j,1]=(int(ff[j,1])&240)|int(np.clip(g+v,0,15))
    elif op==7:
        k=int(rng.integers(8));j=min(n-1,i+1)
        j2=2+k//2;shift=4*(k%2);q=(int(ff[i,j2])>>shift)&15;qn=(int(ff[j,j2])>>shift)&15
        if q==qn:return None
        quant_edit(ff,i,k,1 if qn>q else -1)
    elif op==8:
        j=min(n-1,i+1); half=int(rng.integers(2));s=2+half*2
        ff[i,s:s+2]=ff[j,s:s+2]
    elif op==9:
        j=i+1
        if j>=n or (dd[i],dd[j]) not in [(64,128),(128,64)]:return None
        dd[i],dd[j]=dd[j],dd[i]
    if np.array_equal(ff,f) and np.array_equal(dd,d):return None
    return ff,dd,('edit',op,i)

def split_cand(f,d,rng):
    n=len(f);valid=np.flatnonzero(d>=128)
    if not len(valid):return None
    i=int(rng.choice(valid));duration=int(d[i]);
    # Replace one frame by two frames; the second may take interpolated spectral shape.
    if duration==128:durations=[64,64]
    else:durations=[128,128] if rng.random()<.8 else [64,64,128]
    l=len(durations)
    new=np.tile(f[i:i+1],(l,1))
    if i+1<n:
        nxt=f[i+1]
        if rng.random()<0.45:
            new[-1,0]=nxt[0] if rng.random()<.4 else f[i,0]
            if rng.random()<.4:new[-1,1]=(int(nxt[1])&15)|(int(f[i,1])&48)
        if rng.random()<0.35:
            k=int(rng.integers(8));t=2+k//2;shift=4*(k%2)
            q=(int(new[-1,t])>>shift)&15;qn=(int(nxt[t])>>shift)&15
            if q!=qn:
                q+=1 if qn>q else -1
                new[-1,t]=(int(new[-1,t]) & ~(15<<shift))|(q<<shift)
    ff=np.concatenate([f[:i],new,f[i+1:]],axis=0)
    dd=np.concatenate([d[:i],np.array(durations,np.int32),d[i+1:]],axis=0)
    return ff,dd,('split',i,len(durations))

def run(name,trials,seed,max_splits,verbose=True):
    src=SRC/name/'speech.hq';f,d,_=unpack(src.read_bytes()+b'\xff')
    ref,sr=sf.read(str(ROOT/'references')+'/'+name+'/original.wav'); assert sr==SR
    comp=Compare(ref);base=comp.scores(decode(f,d));base_spec=base[1]
    # Flash: 406 instruction B and one end marker
    max_stream=1024-406-1
    start=evaluate(comp,f,d,max_stream,base_spec)
    assert start is not None
    original_stream=encode(f,d)
    assert original_stream==src.read_bytes()
    rng=np.random.default_rng(seed)
    best=start;accepted=0;split_count=0;split_trials=0;t0=time.monotonic();history=[];events={}
    if verbose:print(name,'baseline',base,'max stream',max_stream,'bytes',len(original_stream),'seed',seed,flush=True)
    for t in range(trials):
        # A higher number of splits is evaluated near start where unused Flash exists.
        is_split=(t%11==0 and split_count<max_splits and len(encode(f,d))<=max_stream-4)
        cand=split_cand(f,d,rng) if is_split else candidate(f,d,rng)
        if cand is None:continue
        ff,dd,edit=cand
        if is_split:split_trials+=1
        met=evaluate(comp,ff,dd,max_stream,base_spec)
        if met is None:continue
        # strict improvement, with spectrum penalty. Bound severe spectral degradation.
        if met[0]>best[0]+0.000018:
            f,d=ff,dd;best=met;accepted+=1;events[str(edit[1])]=events.get(str(edit[1]),0)+1
            if edit[0]=='split':split_count+=1
            history.append([t,round(best[1],7),round(best[2],6),int(best[3]),edit[0],edit[1],edit[2]])
            if verbose and (accepted%6==0 or (best[1]>=0.90 and name=='chego')):
                print(name,'iter',t,'accepted',accepted,'STOI',round(best[1],7),'spec',round(best[2],4),'stream',best[3],'split',split_count,'seconds',round(time.monotonic()-t0,1),flush=True)
            if name=='chego' and best[1]>=.9005:break
        if verbose and t and t%1800==0:
            print(name,'progress',t,'STOI',round(best[1],6),'stream',best[3],'seconds',round(time.monotonic()-t0,1),flush=True)
    report={'phrase':name,'baseline':{'stoi':base[0],'spec':base[1],'bytes':len(original_stream)},
            'final':{'stoi':best[1],'spec':best[2],'bytes':best[3]},'n_frames':len(f),'splits_accepted':split_count,'splits_evaluated':split_trials,
            'accepted':accepted,'trials':t+1,'seconds':round(time.monotonic()-t0,2),'seed':seed,'history':history}
    dst=ROOT/name;dst.mkdir(exist_ok=True)
    (dst/'speech.hq').write_bytes(encode(f,d))
    np.savez(dst/'optimized_frames.npz',frames=f,durations=d)
    (dst/'optimization.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    if verbose:print('RESULT',name,report['final'],'accepted',accepted,'elapsed',report['seconds'],flush=True)
    return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--phrase',choices=['chego','otvechaesh','vinni'],required=True)
 p.add_argument('--max-trials',type=int,default=4000);p.add_argument('--seed',type=int,default=1437);p.add_argument('--max-splits',type=int,default=18)
 a=p.parse_args();run(a.phrase,a.max_trials,a.seed,a.max_splits)
