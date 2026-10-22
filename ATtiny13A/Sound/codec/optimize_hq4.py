#!/usr/bin/env python3
"""Feedback encoder for new-only MiniLPC HQ3 bitstream.
Does not re-train a legacy format. Evaluates exact signed 8-bit AVR lattice output,
then performs stochastic search under Flash and click constraints. Keeps checkpoints.
Usage: python optimize_hq4.py --clip chego --seconds 60 --seed 2026
"""
import argparse,time,random,sys,json
from pathlib import Path
import numpy as np
import soundfile as sf
from pystoi import stoi
from hq4_core import CLIPS,REF,BASE,load,pack_stream,decode

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'trained';OUT.mkdir(exist_ok=True)
# Models must match known releases before optimization.

def stoi_value(ref,pcm):return float(stoi(ref,(pcm.astype(np.float32)-128)/128,7500,extended=False))

def spec(ref,pcm):
    # A low-cost perceptual audit metric; not part of the greedy objective.
    a=np.asarray(ref,dtype=np.float32)
    b=(pcm.astype(np.float32)-128)/128
    win=np.hanning(256).astype(np.float32)
    ix=np.arange(0,len(a)-256,128)
    if len(ix)==0: return 0
    x=np.stack([a[z:z+256] for z in ix])*win
    y=np.stack([b[z:z+256] for z in ix])*win
    v=np.fft.rfft(x,axis=1);w=np.fft.rfft(y,axis=1)
    return float(np.mean(np.abs(np.log(np.maximum(np.abs(v),.006))-np.log(np.maximum(np.abs(w),.006)))))

def clicks(pcm,thr=48):return int(np.sum(np.abs(np.diff(pcm.astype(np.int16)))>=thr))

def setk(row,k,q):
    v=int(row[2+k//2]);row[2+k//2]=(v&240)|q if k%2==0 else (v&15)|(q<<4)

def getk(row,k):return (int(row[2+k//2])>>(4*(k&1)))&15

def budget_of(f,d):return len(pack_stream(f,d))

def optimize(name,seconds=45,seed=0,preset='stoi',base_npz=None):
    ref,sr=sf.read(REF/name/'original.wav');assert sr==7500
    b,f,d,_=load(name)
    if base_npz:
        npz=np.load(base_npz);f=npz['frames'].copy();d=npz['durations'].copy()
    elif (OUT/name/'best.npz').exists():
        p=OUT/name/'best.npz';npz=np.load(p);f=npz['frames'].copy();d=npz['durations'].copy()
    f=f.copy();d=d.copy()
    (OUT/name).mkdir(exist_ok=True)
    code_bytes=406
    max_stream=1024-code_bytes-1
    initial=decode(f,d,0)
    baseline_st=stoi_value(ref,initial);base_spec=spec(ref,initial);base_click=clicks(initial)
    if base_click:print('WARNING: baseline had clicks',base_click)
    best_global_score=baseline_st
    current_st=baseline_st;best=f.copy();current_s=base_spec
    rng=random.Random(seed);start=time.monotonic();checks=0;accepted=0;rounds=0
    states=[0,0,0]
    print(f'{name}: start STOI {baseline_st:.7f} spec {base_spec:.5f} bytes {budget_of(f,d)} frames {len(f)}',flush=True)
    triallog=[]
    # Greedy coordinate descent, then correlated two-frame proposal. Always deterministic per seed.
    def evaluate(candidates,frameidx,orig):
        nonlocal current_st,current_s,best_global_score,best,checks,accepted
        bestrow=None;bs=current_st;bspec=current_s
        for trial in candidates:
            if not np.array_equal(f[frameidx],orig): f[frameidx]=orig
            f[frameidx]=trial
            if budget_of(f,d)>max_stream:continue
            pcm=decode(f,d,0)
            # Reject large abrupt steps, and avoid clipped samples (excess distortion).
            if clicks(pcm)>base_click:continue
            s=stoi_value(ref,pcm);checks+=1
            if s>bs+0.000003:
                new_spec=spec(ref,pcm)
                # Maximum 6% relative worsening to maintain intelligible timbre.
                if new_spec<=base_spec*1.06:
                    bs=s;bspec=new_spec;bestrow=trial.copy()
        f[frameidx]=orig if bestrow is None else bestrow
        if bestrow is not None:
            current_st=bs;current_s=bspec;accepted+=1
            if current_st>best_global_score:
                best_global_score=current_st;best=f.copy()
            if accepted%10==0:
                print(f'{name} accept={accepted} eval={checks} stoi={current_st:.6f} spec={current_s:.4f} stream={budget_of(f,d)}',flush=True)
        return bestrow is not None
    stop=False
    while time.monotonic()-start <seconds and rounds<10:
        order=list(range(len(f)))
        if rounds%2:order.reverse()
        else:rng.shuffle(order)
        for idx in order:
            if time.monotonic()-start>=seconds:break
            row=f[idx].copy()
            # Two most promising frame-level changes from speech modeling: pitch/gain.
            dims=[0,1,2,3]+list(range(4,12))
            if rounds%2:rng.shuffle(dims)
            for dim in dims:
                if time.monotonic()-start>=seconds:break
                orig=f[idx].copy();new=[]
                if dim==0:
                    p=int(orig[0]);
                    vs=sorted({p-8,p-6,p-4,p-3,p-2,p-1,p+1,p+2,p+3,p+4,p+6,p+8,int(round(p*.75)),int(round(p*1.25)),p//2,p*2,0})
                    for v in vs:
                        if (v==0 or 16<=v<=126) and v!=p:
                            rr=orig.copy();rr[0]=v;new.append(rr)
                elif dim==1:
                    g=int(orig[1])&15; h=int(orig[1])&0x30
                    for v in range(max(0,g-3),min(15,g+3)+1):
                        if v!=g:rr=orig.copy();rr[1]=h|v;new.append(rr)
                elif dim==2:
                    m=(int(orig[1])>>4)&3
                    for v in range(4):
                        if v!=m:rr=orig.copy();rr[1]=(int(orig[1])&15)|(v<<4);new.append(rr)
                elif dim==3:
                    p=int(orig[0]);g=int(orig[1])&15
                    for pp,gg in [(-2,1),(2,-1),(-1,2),(1,-2),(-2,-1),(2,1),(-1,-1),(1,1)]:
                        if 16<=p+pp<=126 and 0<=g+gg<=15:
                            rr=orig.copy();rr[0]=p+pp;rr[1]=(rr[1]&0x30)|(g+gg);new.append(rr)
                else:
                    k=dim-4;q=getk(orig,k)
                    for v in sorted({q-3,q-2,q-1,q+1,q+2,q+3}):
                        if 0<=v<=15:
                            rr=orig.copy();setk(rr,k,v);new.append(rr)
                if new:evaluate(new,idx,orig)
        rounds+=1
        triallog.append({'round':rounds,'seconds':round(time.monotonic()-start,1),'stoi':current_st,'spec':current_s,'stream_bytes':budget_of(f,d),'accepted':accepted,'evaluated':checks})
        print(f'{name} END ROUND {rounds} stoi={current_st:.7f} checks={checks} seconds={time.monotonic()-start:.1f}',flush=True)
    if current_st<best_global_score:f=best
    best_pcm=decode(f,d,0)
    final_st=stoi_value(ref,best_pcm)
    np.savez(OUT/name/'best.npz',frames=f,durations=d)
    (OUT/name/'speech.hq').write_bytes(pack_stream(f,d))
    (OUT/name/'expected_pcm.raw').write_bytes(best_pcm.tobytes())
    info={'name':name,'seed':seed,'baseline_stoi':baseline_st,'final_stoi':final_st,
          'baseline_spec':base_spec,'final_spec':spec(ref,best_pcm),'clicks_48':clicks(best_pcm),
          'speech_bytes':budget_of(f,d),'flash_estimated':code_bytes+budget_of(f,d)+1,
          'runtime_s':round(time.monotonic()-start,3),'trials':checks,'accepted':accepted,'rounds':rounds,'history':triallog}
    (OUT/name/'training.json').write_text(json.dumps(info,indent=2,ensure_ascii=False))
    print('FINAL '+json.dumps({k:v for k,v in info.items() if k!='history'},ensure_ascii=False),flush=True)
    return info

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--clip',choices=CLIPS,required=True);p.add_argument('--seconds',type=int,default=45);p.add_argument('--seed',type=int,default=20071);p.add_argument('--base');ar=p.parse_args()
    optimize(ar.clip,ar.seconds,ar.seed,base_npz=ar.base)
