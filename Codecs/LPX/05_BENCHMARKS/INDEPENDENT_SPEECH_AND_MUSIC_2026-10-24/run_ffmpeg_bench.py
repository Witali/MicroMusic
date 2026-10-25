#!/usr/bin/env python3
"""Reproducible fair-ish narrowband 8k 16bit WAV vs Opus and AAC-LC benchmark.
Keep source copyright/licensing separate. Uses real output file bytes incl. container.
"""
import subprocess, json, sys
from pathlib import Path
import soundfile as sf, numpy as np
from scipy.signal import correlate
from pystoi import stoi
ROOT=Path(__file__).resolve().parent
BITRATES=(12,16,24,32,40)
SPEECH={'english_dialogue_20s'}
def cmd(*args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-1000:])

def metrics(a,b,speech=False):
 a=np.asarray(a,dtype=np.float64);b=np.asarray(b,dtype=np.float64)
 # Delay estimate +/- 160 ms. Compare unamplified aligned samples, no gain matching.
 A=a-a.mean();B=b-b.mean()
 cor=correlate(A,B,mode='full',method='fft')
 lags=np.arange(-len(b)+1,len(a))
 eligible=np.abs(lags)<=1280
 lag=int(lags[eligible][np.argmax(cor[eligible])])
 aa=a[max(0,lag):];bb=b[max(0,-lag):]
 n=min(len(aa),len(bb));aa=aa[:n];bb=bb[:n]
 e=aa-bb
 ser=10*np.log10(max(np.sum(aa*aa),1e-30)/max(np.sum(e*e),1e-30))
 ret={'lag_samples':lag,'ser_db':round(float(ser),3),'n_eval':n}
 if speech and n>4000:
  ret['stoi']=round(float(stoi(aa,bb,8000,extended=False)),5)
 return ret

def main():
 rows=[]
 for inp in sorted((ROOT/'references').glob('*.wav')):
  ref,sr=sf.read(inp,dtype='float64');assert sr==8000
  duration=len(ref)/8000
  for codec in ['Opus','AAC-LC']:
   for kbps in BITRATES:
    ext='.opus' if codec=='Opus' else '.m4a'
    target=ROOT/'encoded'/f'{inp.stem}_{codec.lower().replace("-","")}_{kbps}{ext}'
    out=ROOT/'decoded'/f'{target.stem}.wav'
    args=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(inp),'-c:a','libopus' if codec=='Opus' else 'aac','-b:a',f'{kbps}k','-ac','1','-ar','8000']
    if codec=='Opus':args+=['-application','audio','-vbr','on','-compression_level','10']
    cmd(*(args+[str(target)]))
    cmd('ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(target),'-ar','8000','-ac','1','-c:a','pcm_s16le',str(out))
    pcm,_=sf.read(out,dtype='float64')
    vals=metrics(ref,pcm,inp.stem in SPEECH)
    row={'sample':inp.stem,'seconds':duration,'codec':codec,'target_kbps':kbps,'file_bytes':target.stat().st_size,'effective_kbps':round(8*target.stat().st_size/(1000*duration),3),**vals}
    rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 (ROOT/'results'/'ffmpeg_results.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
 return rows
if __name__=='__main__':main()
