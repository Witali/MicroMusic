#!/usr/bin/env python3
"""Closed-loop spectral optimization with near-constant intelligibility.
Tests actual quantized AVR synthesis, no changed decoder and no synthetic labels.
Writes reproducible optimized frame arrays and a machine-readable report.
"""
import argparse,json,time,sys
from pathlib import Path
import numpy as np,soundfile as sf

from model import decode
from quality import Compare
from optimize_hq4 import quant_edit,SRC,ROOT
from hq4_codec import unpack,encode

def run(name,passes=2,min_stoi_drop=0.00015):
    source=ROOT/name/'optimized_frames.npz'
    if source.exists():
        a=np.load(source);frames=a['frames'].copy();durations=a['durations'].copy()
    else:frames,durations,_=unpack((SRC/name/'speech.hq').read_bytes()+b'\xff')
    ref,sr=sf.read(str(ROOT/'references')+'/'+name+'/original.wav');assert sr==7500
    comp=Compare(ref);start=comp.scores(decode(frames,durations));orig_stoi=start[0];
    best=comp.scores(decode(frames,durations));accepted=0;checked=0; t0=time.monotonic();history=[]
    for it in range(passes):
        inds=list(range(len(frames)));inds=inds[::-1] if it%2 else inds
        for i in inds:
            before=frames[i].copy();optrow=None; optmet=best
            ops=[]
            for k in range(8):
                for val in (-2,-1,1,2):ops.append(('coeff',k,val))
            for p in (-2,-1,1,2):ops.append(('pitch',p,None))
            for g in (-2,-1,1,2):ops.append(('gain',g,None))
            for m in range(4):ops.append(('mode',m,None))
            for op,k,v in ops:
                row=frames[i].copy()
                if op=='coeff':quant_edit(frames,i,k,v)
                elif op=='pitch':
                    p=int(frames[i,0]);q=p+k
                    if p==0 or not (16<=q<=126):continue
                    frames[i,0]=q
                elif op=='gain':
                    g=int(frames[i,1])&15;q=g+k
                    if not 0<=q<=15:continue
                    frames[i,1]=(int(frames[i,1])&240)|q
                else:
                    if ((int(frames[i,1])>>4)&3)==k:continue
                    frames[i,1]=(int(frames[i,1])&15)|(k<<4)
                checked+=1
                if len(encode(frames,durations))<=617:
                    y=decode(frames,durations)
                    if not np.any(np.abs(np.diff(y.astype(np.int16)))>=48):
                        spec=comp.spec(y)
                        # Only evaluate expensive STOI if spectral change improves materially
                        if spec < optmet[1]-0.00065:
                            met=comp.scores(y)
                            if met[0]>=orig_stoi-min_stoi_drop and met[1]<optmet[1]-0.00065:
                                optrow=frames[i].copy();optmet=met
                frames[i]=row
            if optrow is not None:
                frames[i]=optrow;best=optmet;accepted+=1
                history.append({'pass':it,'frame':i,'stoi':float(best[0]),'spectral_error':float(best[1]),'stream_bytes':len(encode(frames,durations))})
                if accepted%8==0:print(name,'pass',it,'accepted',accepted,'STOI',round(best[0],6),'spec',round(best[1],5),'bytes',len(encode(frames,durations)),'elapsed',round(time.monotonic()-t0,1),flush=True)
        print(name,'completed pass',it+1,'STOI',round(best[0],6),'spec',round(best[1],5),'accepted',accepted,'elapsed',round(time.monotonic()-t0,1),flush=True)
    # accept only if STOI and spectral combined meet hard constraints
    if best[1] > start[1] or best[0] < orig_stoi-min_stoi_drop:raise RuntimeError('not acceptable')
    result={'phrase':name,'initial_stoi':start[0],'initial_spectral':start[1],'final_stoi':best[0],'final_spectral':best[1],
            'accepted':accepted,'evaluated':checked,'elapsed':round(time.monotonic()-t0,2),'frames':len(frames),
            'data_bytes':len(encode(frames,durations)),'history':history}
    dst=ROOT/name;dst.mkdir(exist_ok=True)
    np.savez(dst/'timbre_frames.npz',frames=frames,durations=durations)
    (dst/'timbre_speech.hq').write_bytes(encode(frames,durations))
    (dst/'timbre_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('RESULT',name,round(best[0],7),round(best[1],5),'accepted',accepted,'elapsed',result['elapsed'],flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phrase',required=True);p.add_argument('--passes',type=int,default=2);p.add_argument('--min-stoi-drop',type=float,default=0.00015)
    a=p.parse_args();run(a.phrase,a.passes,a.min_stoi_drop)
