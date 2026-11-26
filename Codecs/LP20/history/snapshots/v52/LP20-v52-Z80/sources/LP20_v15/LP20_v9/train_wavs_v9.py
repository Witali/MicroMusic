#!/usr/bin/env python3
"""Train one frozen dictionary from independent WAV files. Keep evaluation
voices out of this list. For large corpora sample a bounded balanced subset;
this in-memory trainer is not a streaming multi-hour trainer."""
import argparse,numpy as np
from pathlib import Path
import study as s
from train_class import train
p=argparse.ArgumentParser(description=__doc__);p.add_argument('wav',nargs='+');p.add_argument('--out',required=True);p.add_argument('--kind',choices=['class','rounded'],default='class');p.add_argument('--max-sec-per-file',type=float,default=20.);p.add_argument('--max-total-sec',type=float,default=240.);p.add_argument('--augment',action='store_true');a=p.parse_args();rng=np.random.default_rng(20261126);inp=[];maxlen=int(a.max_sec_per_file*s.FS);total=int(a.max_total_sec*s.FS);paths=list(a.wav);rng.shuffle(paths)
for fn in paths:
 if total<=0:break
 t=s.load(fn);n=min(len(t),maxlen,total)
 if n<s.FS:continue
 start=int(rng.integers(0,len(t)-n+1));inp.append(t[start:start+n]);total-=n
assert inp,'No suitable speech';print('selected training seconds',sum(map(len,inp))/s.FS)
if a.augment:inp=inp+[x*.55 for x in inp[:max(1,len(inp)//3)]]
ww=np.load(s.ROOT/'models/pooled_model.npz')['ww'];np.savez(a.out,**train(inp,ww,a.kind));print('saved',a.out)
