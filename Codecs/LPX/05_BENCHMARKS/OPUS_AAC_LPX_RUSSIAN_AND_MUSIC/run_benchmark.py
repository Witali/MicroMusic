#!/usr/bin/env python3
"""Reproducible 8k/mono LPX comparison with ffmpeg libopus/AAC.
LPX files are prebuilt and tuned on this audio, so comparison is in-sample.
External open-corpus files are not included; use prepare_sources.sh externally.
"""
import argparse, hashlib, io, json, pathlib, shutil, subprocess, sys, wave, zipfile
import numpy as np
import soundfile as sf
from scipy.signal import correlate
from pystoi import stoi

ROOT=pathlib.Path(__file__).resolve().parent
SRC=ROOT/'data'; OUT=ROOT/'encoded'; OUT.mkdir(exist_ok=True)
ZFILE=ROOT/'MicroMusic_LPX3_LPX4_COMPLETE_AGENT_HANDOFF_2026-10-23.zip'
RATE=8000

def shell(args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE, text=True)
 if p.returncode: raise RuntimeError(p.stderr+' command '+repr(args))
 return p.stdout

def get_wav(fn):
 y,sr=sf.read(fn, dtype='float64')
 if sr!=RATE: raise ValueError((fn,sr))
 if y.ndim>1:y=y.mean(axis=1)
 return y

def extract():
 SRC.mkdir(exist_ok=True)
 if ZFILE.exists():
  z=zipfile.ZipFile(ZFILE)
  for name,stem in [('chego','chego'),('otvechaesh','otvet')]:
   prefix=f'08_PRIVATE_EVIDENCE/CURRENT_Q0_EXAMPLES/{name}/'
   mapping={
    'original_pcm16.wav': f'{stem}_reference.wav',
    'optimized_pcm16_wav.wav': f'{stem}_lpx4.wav',
    'source_legacy.lpx3': f'{stem}_lpx3_v1.lpx3',
    'optimized_l4hy.l4hy': f'{stem}_lpx4.l4hy',
    'source_v1.l3av': f'{stem}_lpx3_vbr.l3av'
   }
   for n,target in mapping.items():
    (SRC/target).write_bytes(z.read(prefix+n))
  files=[n for n in z.namelist() if '08_PRIVATE_EVIDENCE/ORIGINAL_USER_RECORDINGS/vinni-pux' in n]
  if files:(SRC/'vinni_source.mp3').write_bytes(z.read(files[0]))
  # Waveforms of other legacy LPX versions, if present in mounted directory
 for stem,original in [('chego','MicroMusic_LPX3_RiceV5_Chego_tebe_nuzhno.wav'),('otvet','MicroMusic_LPX3_RiceV5_Chto_zh_ty_ne_otvechaesh.wav')]:
  sp=ROOT.parent / original
  if sp.exists():
   y,sr=sf.read(sp,dtype='float64')
   if sr==8000 and len(y)==len(get_wav(SRC/f'{stem}_reference.wav')):
    # these are pcm_u8 wav from v5; v7 streams produce identical PCM
    shutil.copy(sp, SRC/f'{stem}_lpx3_rice.wav')

# Compute segment SNR without amplitude fit; alignment by max cross-correlation.
def compare(ref, decoded, allow_shift=True):
 r=np.asarray(ref,dtype=np.float64); d=np.asarray(decoded,dtype=np.float64)
 lag=0
 if allow_shift:
  x=r-r.mean(); y=d-d.mean(); maxlag=min(1024,len(r)//4)
  if len(d)>=len(r)//2:
   corr=correlate(x,y,mode='full',method='fft')
   ll=np.arange(-len(y)+1,len(x))
   valid=(ll>=-maxlag)&(ll<=maxlag)
   lag=int(ll[valid][np.argmax(corr[valid])])
 if lag>=0: a=r[lag:]; b=d[:len(a)]
 else: a=r[:len(r)+lag]; b=d[-lag:]
 n=min(len(a),len(b)); a=a[:n]; b=b[:n]
 if n < 8000//4:return {'lag':lag,'error':'no_overlap'}
 q=np.sum(a*a)/max(np.sum((a-b)**2),1e-30)
 return {'ser_db':float(10*np.log10(q)),'stoi':float(stoi(a,b,RATE,extended=False)),
         'lag':lag,'n_used':n,'corr':float(np.corrcoef(a,b)[0,1])}

def read_raw(fn):
 return np.fromfile(fn, dtype='<i2').astype(np.float64)/32768

def encode(refname, sample, codec, target_kbps):
 wav=SRC/f'{sample}_reference.wav'; output=OUT/f'{sample}_{codec}_{target_kbps}.{ "opus" if codec=="opus" else "m4a"}'
 cmd=['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(wav), '-ac','1','-ar','8000']
 if codec=='opus': cmd+=['-c:a','libopus','-application','audio','-vbr','on','-b:a',f'{target_kbps}k','-frame_duration','20']
 elif codec=='aac': cmd+=['-c:a','aac','-profile:a','aac_low','-b:a',f'{target_kbps}k']
 cmd+=[str(output)]
 shell(cmd)
 raw=OUT/f'{sample}_{codec}_{target_kbps}.s16';
 shell(['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(output),'-ac','1','-ar','8000','-c:a','pcm_s16le','-f','s16le',str(raw)])
 decoded=read_raw(raw); reference=get_wav(wav)
 r=compare(reference,decoded)
 info={'sample':sample, 'codec':codec.upper(), 'target_kbps':target_kbps,
       'bytes':output.stat().st_size,'effective_kbps':round(output.stat().st_size*8/(len(reference)/RATE)/1000,2),
       'duration_s':round(len(reference)/RATE,3), 'reference_samples':len(reference),
       'decoded_samples':len(decoded),**r}
 info['checksum_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
 return info

def process():
 extract()
 rows=[]
 for sample in ['chego','otvet']:
  ref=get_wav(SRC/f'{sample}_reference.wav')
  for codec in ['opus','aac']:
   for kbps in [12,16,24,32,40,48]:
    try:rows.append(encode('speech',sample,codec,kbps))
    except Exception as e:print('ERROR',sample,codec,kbps,e,file=sys.stderr)
  for codec,fn in [('LPX4 Q0',f'{sample}_lpx4.l4hy'),('LPX3 v1',f'{sample}_lpx3_v1.lpx3')]:
   row={'sample':sample,'codec':codec,'bytes':(SRC/fn).stat().st_size,'duration_s':len(ref)/RATE}
   row['effective_kbps']=round(row['bytes']*8/row['duration_s']/1000,2)
   if codec=='LPX4 Q0': row.update(compare(ref,get_wav(SRC/f'{sample}_lpx4.wav'),False))
   else: row['quality_note']='original LPX3 v1 PCM not decoded for this benchmark'
   rows.append(row)
  fn=SRC/f'{sample}_lpx3_rice.wav'
  if fn.exists():
   # Files here are v5, v7 bitstream size from prior verified project
   sizes={'chego':5189,'otvet':4415}
   x=get_wav(fn)
   row={'sample':sample,'codec':'LPX3 Rice v7','bytes':sizes[sample], 'duration_s':len(ref)/RATE,
        'size_note':'v7 stream, PCM from equivalent LPX3 v5 reconstruction',
        'effective_kbps':round(sizes[sample]*8/(len(ref)/RATE)/1000,2)}
   row.update(compare(ref,x,False)); rows.append(row)
 (ROOT/'comparison.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
 import csv
 fields=['sample','codec','target_kbps','bytes','effective_kbps','ser_db','stoi','corr','lag','reference_samples','decoded_samples','quality_note']
 with (ROOT/'comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 print('\n'.join(f"{r['sample']} {r['codec']} {r.get('target_kbps','-'):>3} {r['bytes']:>5}B {r['effective_kbps']:>6}k {r.get('ser_db',float('nan')):7.2f}dB {r.get('stoi',float('nan')):.4f}" for r in rows))

if __name__=='__main__':process()
