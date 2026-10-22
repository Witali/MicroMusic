#!/usr/bin/env python3
"""Rate/distortion search for MiniLPC-HQ. Single native stream, no backward compatibility.
Closed-loop quality is evaluated using the AVR-bit-exact Python synthesizer.
No hidden automatic acceptance: comparison metrics, budgets and all streams saved.
"""
import os,json,time,argparse
from pathlib import Path
import numpy as np,soundfile as sf
from quality import Compare,stft_log
from model import decode
from build_hq import encode
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'baselines'

class Search:
 def __init__(self,name):
  self.name=name
  ref,sr=sf.read(ROOT/'references'/name/'original.wav');assert sr==7500
  self.comp=Compare(ref)
  src=np.load(BASE/f'{name}_refined.npz')
  self.f=src['frames'].copy();self.d=src['dur'].copy()
  previous=ROOT/'samples'/name/'trained.npz'
  if previous.exists():
   x=np.load(previous);self.f=x['frames'].copy();self.d=x['durations'].copy()
  self.voice_budget=1023-412-1
  self.base=self.score(self.f,self.d)[1]
  self.score0=self.quality(self.base)
  self.iterations=0
  self.history=[]
  print(name,'starting',self.score0,'bytes',len(encode(self.f,self.d)[0]),'budget',self.voice_budget,flush=True)
 def score(self,f,d):
  signal=decode(f,d,0)
  # By design never access training outputs from a different decoder.
  return self.quality(signal),signal
 def quality(self,pcm):
  s,sp,c=self.comp.scores(pcm)
  return (s-0.015*sp-0.0025*c),(s,sp,c)
 def streams(self,f,d):return len(encode(f,d)[0])
 def choose_candidates(self):
  out=decode(self.f,self.d,0)
  target=self.comp.log;log=stft_log(out)
  err=np.mean(np.abs(target-log),axis=1)
  timeline=np.cumsum(np.r_[0,self.d.astype(np.int32)])
  scores=[]
  for i,(a,b) in enumerate(zip(timeline[:-1],timeline[1:])):
   ix0=max(0,int((a-100)//128));ix1=min(len(err),int((b+100)//128)+1)
   v=float(np.mean(err[ix0:ix1]))
   # prioritize transients and large voiced errors; still explore all positions eventually
   scores.append((v,i))
  return [i for _,i in sorted(scores,reverse=True)]
 def split(self,i):
  f=self.f;d=self.d
  if d[i]==64:return None
  half=int(d[i])//2
  df=np.insert(d,i+1,half).astype(np.uint16);df[i]=half
  ff=np.insert(f,i+1,f[i],axis=0).astype(np.uint8)
  return ff,df
 def optimize_second(self,ff,dd,i,click_ceiling):
  j=i+1;current=ff[j].copy()
  result,pcm=self.score(ff,dd);self.iterations+=1
  score=result[0]
  st=result[1]
  def attempt(p,g,m,which=None,val=None):
   nonlocal score,st,current
   ff[j]=current.copy()
   old=ff[j].copy()
   ff[j,0]=p;ff[j,1]=(m<<4)|g
   if which is not None:
    oldn=int(ff[j,2+which//2]);vv=(oldn&0xF0)|val if which%2==0 else (oldn&15)|(val<<4)
    ff[j,2+which//2]=vv
   if self.streams(ff,dd)>self.voice_budget:ff[j]=old;return
   result,output=self.score(ff,dd);self.iterations+=1
   nextscore=result[0]
   metrics=result[1]
   if nextscore>score+1e-6 and metrics[2]<=click_ceiling:
    score=nextscore;st=metrics;current=ff[j].copy()
   ff[j]=old
  for dim in (0,1,2,0,1):
   p=int(current[0]);g=int(current[1])&15;m=(int(current[1])>>4)&3
   if dim==0:
    if p==0:pp=[0,16,22,28]
    else:pp=[p,p-1,p+1,p-2,p+2,p-3,p+3,p//2,min(126,p*2),round(p*.75),round(p*1.3),0]
    options=[(v,g,m) for v in sorted(set(int(z) for z in pp)) if v==0 or 15<=v<=126]
   elif dim==1:
    gg=[0,1,2,3,4,6,8,10,12,14,15,g-4,g-2,g-1,g,g+1,g+2,g+4]
    options=[(p,x,m) for x in sorted(set(gg)) if 0<=x<=15]
   else:options=[(p,g,x) for x in range(4)]
   for pc,gc,mc in options:attempt(pc,gc,mc)
   ff[j]=current
  # formant variants are more costly; use small number of single-coefficient tweaks
  for k in range(8):
   old=ff[j].copy();raw=int(current[2+k//2]);kv=(raw>>(4*(k%2)))&15
   for delta in (-2,-1,1,2):
    if 0<=kv+delta<16:
     attempt(int(current[0]),int(current[1])&15,(int(current[1])>>4)&3,k,kv+delta)
   ff[j]=current
  ff[j]=current
  return ff,dd,score,st
 def run(self,time_limit=45,passes=2,max_attempt=150):
  started=time.monotonic()
  result,signal=self.score(self.f,self.d)
  best=result[0]
  prior=result[1]
  order=self.choose_candidates()
  used=set();accept=0
  for ii,i in enumerate(order):
   if ii>=max_attempt or time.monotonic()-started>=time_limit:break
   if i in used:continue
   trial=self.split(i)
   if trial is None:continue
   ff,dd=trial
   if self.streams(ff,dd)>self.voice_budget:continue
   optimized=self.optimize_second(ff,dd,i,prior[2])
   newf,newd,newscore,metric=optimized
   streamlen=self.streams(newf,newd)
   delta=newscore-best
   if delta>0.00017 and metric[0]>=prior[0]-0.0001 and metric[2]<=prior[2]:
    self.f,self.d=newf,newd
    best=newscore;prior=metric;accept+=1
    used={j+1 if j>=i+1 else j for j in used}
    used.add(i)
    info={'i':i,'gain':round(delta,6),'metrics':tuple(float(x) for x in prior),'flash':413+streamlen,'iter':self.iterations}
    self.history.append(info)
    print(self.name,'split',info,flush=True)
   if ii and ii%14==0:print(self.name,'progress',ii,'of',len(order),'elapsed',round(time.monotonic()-started,1), 'accepted',accept,'evals',self.iterations,flush=True)
  final,signal=self.score(self.f,self.d)
  print(self.name,'FINISHED',self.quality(signal)[1],'accepted',accept,'streamlen',self.streams(self.f,self.d),'seconds',round(time.monotonic()-started,1),flush=True)
  dest=ROOT/'samples'/self.name
  np.savez(dest/'trained.npz',frames=self.f,durations=self.d)
  (dest/'training.json').write_text(json.dumps({'name':self.name,'baseline':{'stoi':self.score0[1][0],'spec':self.score0[1][1],'clicks':self.score0[1][2]},'final':{'stoi':prior[0],'spec':prior[1],'clicks':prior[2]},'history':self.history,'elapsed_s':round(time.monotonic()-started,2)},indent=2))
  return accept

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--voice',choices=['chego','otvechaesh','vinni'],required=True);ap.add_argument('--seconds',type=int,default=45);ap.add_argument('--attempts',type=int,default=70)
 args=ap.parse_args()
 t=Search(args.voice);t.run(args.seconds,max_attempt=args.attempts)
