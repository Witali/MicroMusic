#!/usr/bin/env python3
"""Optional spectrum polishing with hard minimum STOI and flash budget.
Does NOT mutate decoder, codec format, or sample rate. Checkpoints are saved only
if spectral distance improves while STOI remains above minimum.
"""
from pathlib import Path
import argparse,json,time
import numpy as np,soundfile as sf
from codec import encode_stream,src_size
from model import decode
from quality import Compare
from optimize import modify
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--voice',choices=['chego','otvechaesh','vinni'],default='chego');p.add_argument('--seconds',type=int,default=18);p.add_argument('--min-stoi',type=float,default=.9001);p.add_argument('--seed',type=int,default=1234);a=p.parse_args()
 src=ROOT/'inputs'/a.voice;dest=ROOT/'results'/a.voice
 x=np.load(dest/'trained.npz');f=x['frames'].copy();d=x['durations'].copy()
 ref,sr=sf.read(src/'original.wav');assert sr==7500
 cm=Compare(ref);code_bytes=src_size(src/'firmware.S')
 def measure(f,d):
  try:bb=encode_stream(f,d)
  except Exception:return None
  if code_bytes+len(bb)>1024:return None
  x=decode(f,d,0);st,sp,click=cm.scores(x)
  return(st,sp,click,len(bb))
 old=measure(f,d);assert old and old[0]>a.min_stoi and old[2]==0
 best=old;accepted=0;tried=0;start=time.monotonic();rng=np.random.default_rng(a.seed)
 while time.monotonic()-start<a.seconds:
  candidate=modify(rng,f,d)
  if candidate is None:continue
  ff,dd,op=candidate;v=measure(ff,dd);tried+=1
  if v and v[2]==0 and v[0]>=a.min_stoi and v[1]<best[1]-0.00003:
   f,d=ff,dd;best=v;accepted+=1
 if best[1]<old[1]:
  np.savez_compressed(dest/'trained.npz',frames=f,durations=d)
  (dest/'speech.hq').write_bytes(encode_stream(f,d,terminator=False))
 (dest/'spectral_polish.json').write_text(json.dumps({'before':old,'after':best,'min_stoi':a.min_stoi,'seed':a.seed,'trials':tried,'accepted':accepted},indent=2))
 print(a.voice,'before',old,'after',best,'accepted',accepted,'trials',tried,flush=True)
if __name__=='__main__':main()
