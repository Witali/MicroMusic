#!/usr/bin/env python3
"""Closed-loop training of the TWO NEW pulse-profile bits (no old bitstream support).
Works with only the current 6-byte/keyframe format. Requires numpy, numba, soundfile, pystoi.
Run python train_profiles.py --apply to write speech.bin and reference PCM; rebuild + verify afterwards.
Default mode prints current STOI/clicks, without modifying the distributed files.
"""
from pathlib import Path
from argparse import ArgumentParser
import numpy as np
import soundfile as sf
from pystoi import stoi
from model import decode
P=Path(__file__).resolve().parent
NAMES=('chego','otvechaesh','vinni')

def score(packed,ref):
 out=decode(packed)
 y=(out.astype(np.float64)-128.0)/128.0
 y-=y.mean()
 s=stoi(ref,y,7500,extended=False)
 jumps=np.abs(np.diff(out.astype(np.int16)))
 return float(s),int((jumps>=48).sum()),out

def main(voice,apply):
 folder=P/'samples'/voice
 payload=np.frombuffer((folder/'speech.bin').read_bytes(),dtype=np.uint8).copy()
 ref,sr=sf.read(P/'references'/voice/'original.wav')
 assert sr==7500 and len(ref)==len(payload)//6*256
 begin=score(payload,ref)
 if not apply:
  print(voice,'STOI',round(begin[0],5),'clicks',begin[1],'use --apply to optimize')
  return
 best=begin
 frames=[i for i in range(len(payload)//6) if payload[i*6]!=0 and (payload[i*6+1]&15)]
 for epoch in range(3):
  rng=np.random.default_rng(30+epoch)
  updated=0
  for i in rng.permutation(frames):
   off=i*6+1; orig=int(payload[off]);k=orig>>4
   curr=best[0]
   for mode in range(4):
    payload[off]=(orig&15)|(mode<<4)
    candidate=score(payload,ref)
    if candidate[1]<=begin[1] and candidate[0]>curr+0.000035:
     curr=candidate[0];k=mode;b=candidate
   payload[off]=(orig&15)|(k<<4)
   if curr>best[0]+0.000035:
    best=b;updated+=1
  print(voice,'epoch',epoch,'improved frames',updated,'STOI',best[0])
  if not updated:break
 (folder/'speech.bin').write_bytes(payload.tobytes())
 (folder/'expected_pcm.raw').write_bytes(best[2].tobytes())
 print(voice,'old STOI',begin[0],'new STOI',best[0],'old clicks',begin[1],'new clicks',best[1])

if __name__=='__main__':
 a=ArgumentParser();a.add_argument('--apply',action='store_true');a.add_argument('--voice',choices=NAMES)
 args=a.parse_args()
 for name in ([args.voice] if args.voice else NAMES):main(name,args.apply)
