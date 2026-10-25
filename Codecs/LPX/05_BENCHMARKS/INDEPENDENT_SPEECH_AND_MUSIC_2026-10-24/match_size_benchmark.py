#!/usr/bin/env python3
"""Find closest container byte size to LPX3 3bit and LPX4 3bit by tuning FFmpeg target bitrate.
Output includes accurate actual bytes and unadjusted SER after alignment. Handles nonmonotonic AAC bitrates.
"""
import sys, json, subprocess
from pathlib import Path
import numpy as np,soundfile as sf
from run_ffmpeg_bench import metrics
R=Path(__file__).resolve().parent
SAMPLES={
 'english_dialogue_20s':('english','english_3bit.l4hy'),
 'saxophone_16s':('sax','sax_3bit.l4hy'),
 'synthetic_music_12s':('music12','music12_3bit.l4hy')}
def call(args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-600:])
def encode(src,codec,kbps):
 fmt='opus' if codec=='Opus' else 'm4a'
 dest=R/'encoded'/f'{src.stem}_{codec.lower().replace("-","")}_match_{kbps}.{fmt}'
 if dest.exists():return dest
 args=['ffmpeg','-v','error','-nostdin','-y','-i',str(src),'-ar','8000','-ac','1','-c:a','libopus' if codec=='Opus' else 'aac','-b:a',f'{kbps}k']
 if codec=='Opus': args+=['-application','audio','-vbr','on','-compression_level','10']
 call(args+[str(dest)]);return dest

def matched(src,codec,target):
 lo,hi=8,56;try_rates=set()
 for _ in range(7):
  if lo>hi:break
  mid=(lo+hi)//2;try_rates.add(mid)
  f=encode(src,codec,mid)
  if f.stat().st_size<target:lo=mid+1
  else:hi=mid-1
 try_rates.update(range(max(8,lo-2),min(56,lo+3)))
 try_rates.update(range(max(8,hi-2),min(56,hi+3)))
 options=[encode(src,codec,k) for k in try_rates]
 f=min(options,key=lambda x:(abs(x.stat().st_size-target),x.stat().st_size))
 kbps=int(f.stem.rsplit('_',1)[-1]);return f,kbps

def main():
 rows=[]
 for sample,(folder,lp4) in SAMPLES.items():
  root=R/f'lpx3_{folder}'
  targets={'LPX3':root/'voice_v3_3bit.lpx3','LPX4':root/lp4}
  src=R/'references'/f'{sample}.wav';ref,sr=sf.read(src,dtype='float64')
  for name,file in targets.items():
   target=file.stat().st_size
   for codec in ['Opus','AAC-LC']:
    out,k=matched(src,codec,target)
    wav=R/'decoded'/f'{out.stem}.wav'
    call(['ffmpeg','-v','error','-nostdin','-y','-i',str(out),'-ar','8000','-ac','1','-c:a','pcm_s16le',str(wav)])
    y,_=sf.read(wav)
    m=metrics(ref,y,sample=='english_dialogue_20s')
    item={'sample':sample,'compare_to':name,'source_size':target,'codec':codec,'requested_kbps':k,'bytes':out.stat().st_size,'size_delta_percent':round(100*(out.stat().st_size/target-1),2),'effective_kbps':round(out.stat().st_size*8/(1000*len(ref)/sr),2),**m}
    rows.append(item);print(item,flush=True)
 (R/'results'/'matched_sizes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
