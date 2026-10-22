#!/usr/bin/env python3
"""Second objective: improve spectral envelope without losing 0.90 STOI.
Searches candidate local spectral/gain/period edits in exact AVR arithmetic.
"""
import argparse,time,json,random
from pathlib import Path
import soundfile as sf,numpy as np
from hq4_core import REF,decode,pack_stream
from optimize_hq4 import OUT,stoi_value,spec,clicks,getk,setk

def tune(name='chego',seconds=35,floor=0.9005,seed=47):
    path=OUT/name/'best.npz';v=np.load(path);f=v['frames'].copy();d=v['durations'].copy()
    ref,sr=sf.read(REF/name/'original.wav');assert sr==7500
    initial=decode(f,d);vst=stoi_value(ref,initial);vsp=spec(ref,initial)
    print('INIT',name,'STOI',vst,'SPEC',vsp,'MAX',len(pack_stream(f,d)),flush=True)
    if vst<floor:raise ValueError('baseline must be better than STOI minimum')
    clock=time.monotonic();ncheck=0;accepted=0;rounds=0
    rng=random.Random(seed)
    bestsp=vsp;bestst=vst
    while time.monotonic()-clock<seconds and rounds<8:
        order=list(range(len(f)));rng.shuffle(order)
        for idx in order:
            if time.monotonic()-clock>=seconds:break
            for k in rng.sample(list(range(10)),10):
                if time.monotonic()-clock>=seconds:break
                orig=f[idx].copy();choices=[]
                if k<8:
                    q=getk(orig,k)
                    for qq in [q-2,q-1,q+1,q+2]:
                        if 0<=qq<=15:
                            rr=orig.copy();setk(rr,k,qq);choices.append(rr)
                elif k==8:
                    gain=int(orig[1])&15
                    for gg in [gain-2,gain-1,gain+1,gain+2]:
                        if 0<=gg<=15:rr=orig.copy();rr[1]=(int(rr[1])&0x30)|gg;choices.append(rr)
                else:
                    period=int(orig[0])
                    for pp in [period-2,period-1,period+1,period+2]:
                        if 16<=pp<=126:rr=orig.copy();rr[0]=pp;choices.append(rr)
                current=bestsp;winning=None;winSt=bestst
                for rr in choices:
                    f[idx]=rr
                    if len(pack_stream(f,d))>617:continue
                    x=decode(f,d);ncheck+=1
                    if clicks(x)>0:continue
                    st=stoi_value(ref,x)
                    if st<floor:continue
                    ss=spec(ref,x)
                    if ss<current-0.000015:
                        current=ss;winning=rr.copy();winSt=st
                if winning is not None:
                    f[idx]=winning;bestsp=current;bestst=winSt;accepted+=1
                    if accepted%10==0:print('ACCEPT',accepted,'STOI',bestst,'SPEC',bestsp,flush=True)
                else:f[idx]=orig
        rounds+=1;print('ROUND',rounds,'STOI',bestst,'SPEC',bestsp,flush=True)
    pcm=decode(f,d)
    np.savez(path,frames=f,durations=d)
    (OUT/name/'speech.hq').write_bytes(pack_stream(f,d));(OUT/name/'expected_pcm.raw').write_bytes(pcm.tobytes())
    obj={'initial_stoi':vst,'final_stoi':bestst,'initial_spec':vsp,'final_spec':bestsp,'floor':floor,'samples':len(pcm),'accepted':accepted,'checks':ncheck,'seconds':round(time.monotonic()-clock,2)}
    (OUT/name/'timbre_refine.json').write_text(json.dumps(obj,indent=2))
    print('FINAL',json.dumps(obj),flush=True)

if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('--clip',default='chego');pa.add_argument('--seconds',type=int,default=35);pa.add_argument('--floor',type=float,default=.9005);a=pa.parse_args();tune(a.clip,a.seconds,a.floor)
