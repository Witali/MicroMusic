#!/usr/bin/env python3
"""Reproducible annealed closed-loop search on packed HQ3-only frame format.
Search accepts some temporarily worse candidates, but writes best valid
checkpoint only after STOI / spectral / click / Flash checks.
"""
import sys,json,time,math,argparse
from pathlib import Path
import numpy as np,soundfile as sf

from model import decode
from quality import Compare
from optimize_hq4 import candidate,split_cand,SRC,ROOT
from hq4_codec import unpack,encode

def run(name,trials,seed):
 orig,d,_=unpack((SRC/name/'speech.hq').read_bytes()+b'\xff')
 ref,sr=sf.read(str(ROOT/'references')+'/'+name+'/original.wav')
 cp=Compare(ref);base=cp.scores(decode(orig,d)); start=base[0]-.004*base[1]
 rng=np.random.default_rng(seed);best=(start,orig.copy(),d.copy(),base);cur_f=orig.copy();cur_d=d.copy();cur_score=start
 valid=0;accepted=0;changes=0;t0=time.monotonic();hist=[]
 for z in range(trials):
  if z%500==0:cur_f,cur_d,cur_score=best[1].copy(),best[2].copy(),best[0]
  if z%6==0:
   cand=split_cand(cur_f,cur_d,rng)
  else:
   cand=candidate(cur_f,cur_d,rng)
  if cand is None:continue
  ff,dd,op=cand
  if z%5==0 and op[0]=='edit':
   nextc=candidate(ff,dd,rng)
   if nextc is not None:ff,dd,_=nextc
  bb=encode(ff,dd)
  if len(bb)>617:continue
  y=decode(ff,dd)
  if np.any(np.abs(np.diff(y.astype(np.int16)))>=48):continue
  met=cp.scores(y); valid+=1
  score=met[0]-.004*met[1]
  if score>best[0]+.000012 and met[0]>=base[0]-0.0001 and met[1]<=base[1]+.02:
   best=(score,ff.copy(),dd.copy(),met);changes+=1
   hist.append({'iteration':z,'stoi':met[0],'spec':met[1],'bytes':len(bb)})
   print(name,'NEW BEST',z,'STOI',round(met[0],7),'spec',round(met[1],5),'flash',len(bb)+407,'secs',round(time.monotonic()-t0,1),flush=True)
  temperature=.0004*(1-((z%500)/500))+.00005
  if score>cur_score or rng.random()<math.exp(max(-30,(score-cur_score)/temperature)):
   cur_f,cur_d,cur_score=ff,dd,score;accepted+=1
  if z and z%2200==0:print(name,'progress',z,'best',best[3][:2],'valid',valid,'accepted',accepted,'sec',round(time.monotonic()-t0,1),flush=True)
 path=ROOT/name;path.mkdir(exist_ok=True)
 np.savez(path/'anneal_best.npz',frames=best[1],durations=best[2]);(path/'anneal_speech.hq').write_bytes(encode(best[1],best[2]))
 report={'name':name,'baseline':base,'best':best[3],'bytes':len(encode(best[1],best[2])),'attempts':trials,'valid':valid,'accepted':accepted,'improvements':changes,'seconds':round(time.monotonic()-t0,2),'seed':seed,'history':hist}
 (path/'anneal_report.json').write_text(json.dumps(report,indent=2));print('RESULT',name,report['best'],'flash',report['bytes']+407,'s',report['seconds'],flush=True)
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--phrase',required=True);p.add_argument('--trials',type=int,default=6000);p.add_argument('--seed',type=int,default=2001);a=p.parse_args();run(a.phrase,a.trials,a.seed)
