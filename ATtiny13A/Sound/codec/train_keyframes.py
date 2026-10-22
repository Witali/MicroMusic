#!/usr/bin/env python3
"""Analysis-by-synthesis optimizer for compact LPC8 keyframes, deterministic.
Select omitted formant keyframes to fit ATtiny13A Flash, then tune codebook
parameters with bit-exact decoder model against the original and LPX3 voices.
"""
import argparse,json,time,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

from model_keyframes import render,packed_size
from package_stream import pack
from perceptual import load_wav,Evaluator

def score(m):
    return 3.0*m['stoi']-0.42*m['mel_original']-0.23*m['mel_lpc2']-0.0008*m['clicks_48']

def run(clip,skips=3, budget=800, seed=729):
    p=ROOT/'datasets'/clip
    data=np.load(p/'seed_parameters.npz')
    K=np.asarray(data['K'],np.int64).copy(); P=np.asarray(data['P'],np.int64).copy(); E=np.asarray(data['E'],np.int64).copy()
    orig=load_wav(p/'original.wav')
    lpx=load_wav(p/'lpx3_voice.wav')
    ev=Evaluator(orig,lpx)
    n=len(P)*256
    baseline=np.fromfile(p/'baseline_pcm_u8.raw',np.uint8).astype('int16')-128
    before=ev.metrics(baseline)
    mask=(E>0).astype(np.uint8)
    def evaluate(fast=False):
        wave=render(K,P,E,mask,n,4,4)
        m=ev.metrics(wave,fast=fast)
        return wave,m,score(m)
    _,allm,_=evaluate()
    # Greedy removal of keys; selecting most acoustically redundant, not every-other frame.
    skips=min(skips, int(sum(E>0))-1)
    removals=[]
    for s in range(skips):
        best=None
        for idx in np.flatnonzero(mask):
            if idx==np.flatnonzero(mask)[0]:continue
            mask[idx]=0
            _,met,val=evaluate()
            mask[idx]=1
            if best is None or val>best[0]:best=(val,int(idx),met)
        if best is None:break
        _,idx,met=best;mask[idx]=0
        removals.append(idx)
    before_opt_wave,start_m,start_sc=evaluate()
    rng=np.random.default_rng(seed)
    key_indices=np.flatnonzero(mask)
    voiced=np.flatnonzero(E>0)
    samples=0;accept=0; history=[]
    start=time.monotonic()
    cur=start_sc
    for i in range(budget):
        action=int(rng.integers(0,10))
        if action<7:
            j=int(rng.choice(key_indices))
            k=int(rng.integers(0,8))
            old=int(K[j,k]);v=int(np.clip(old+int(rng.choice([-2,-1,1,2])),-7,7))
            if v==old:continue
            K[j,k]=v
        elif action<9:
            j=int(rng.choice(voiced));old=int(E[j]);v=int(np.clip(old+int(rng.choice([-2,-1,1,2])),1,15))
            if v==old:continue
            E[j]=v;k=-1
        else:
            j=int(rng.choice(voiced));old=int(P[j]);v=int(np.clip(old+int(rng.choice([-2,-1,1,2])),0,63))
            if v==old:continue
            P[j]=v;k=-1
        _,met,val=evaluate()
        samples+=1
        if val>cur+1e-7 and met['clicks_60']<=max(start_m['clicks_60']+2,4):
            cur=val;accept+=1
            history.append({'try':samples,'f':j,'which':action,'k':k,'from':old,'to':v,'score':cur})
        else:
            if action<7:K[j,k]=old
            elif action<9:E[j]=old
            else:P[j]=old
        if (i+1)%200==0:
            print(clip,'step',i+1,'accepted',accept,'score',round(cur,4),'STOI',round(met['stoi'],4),'elapsed',round(time.monotonic()-start,1),flush=True)
    bestwave,finalm,finalscore=evaluate()
    speech,events=pack(K,P,E,mask)
    size_estimate=834+len(speech)+1
    out=ROOT/clip;out.mkdir(parents=True,exist_ok=True)
    (out/'voice_tinylpc.bin').write_bytes(speech)
    np.savez(out/'trained_parameters.npz',K=K,P=P,E=E,mask=mask)
    import soundfile as sf
    sf.write(out/'model_keyframes.wav',bestwave.astype('float64')/128,7500,subtype='PCM_16')
    report={'clip':clip,'frames':len(P),'keyframes':sum(x[0]=='key' for x in events), 'short_updates':sum(x[0]=='predict' for x in events),'silence_runs':sum(x[0]=='silence' for x in events),
           'speech_bytes':len(speech),'estimated_flash':size_estimate,'removed_keyframes':removals, 'baseline_LPC8':before,'all_keyframes_smooth':allm,
           'selected_keyframes_before_optimizer':start_m,'optimized':finalm,'score_initial':start_sc,'score_optimized':finalscore,
           'optimization_proposals':samples,'accepted':accept,'training_seconds':time.monotonic()-start}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (out/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--clip',choices=['xtuj-ntt','ne-otv'],required=True)
    ap.add_argument('--skips',type=int,default=3)
    ap.add_argument('--budget',type=int,default=800)
    args=ap.parse_args()
    run(args.clip,args.skips,args.budget)
